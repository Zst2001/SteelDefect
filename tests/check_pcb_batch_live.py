"""Opt-in batch acceptance using disposable MySQL/Redis and real CPU/HTTP/browser.

No daily environment, ports, user data or external network. Synthetic images only.
"""
import argparse
import base64
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import threading

from check_pcb_infrastructure import ROOT, bootstrap, docker
from check_pcb_classification_live import child, port, stop


def main():
    if len(sys.argv)>1 and sys.argv[1] in {"--api","--worker","--burst"}:
        child(*sys.argv[1:]);return
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists():raise RuntimeError("Fresh evidence directory required")
    out.mkdir(parents=True)
    report={"status":"RUNNING","assertions":[],"scope":"isolated real MySQL/Redis/RQ/CPU/browser; synthetic images"}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        report["assertions"].append(label)
    containers=[];processes=[];logs=[];engine=None
    label="steel.pcb.batch.acceptance="+uuid.uuid4().hex
    env={**os.environ,"PYTHONIOENCODING":"utf-8","PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"}
    try:
        for image,internal,extra in (
            ("mysql:8.0",3306,["--env","MYSQL_ALLOW_EMPTY_PASSWORD=yes","--env","MYSQL_DATABASE=steel_lab_test_pcb","--tmpfs","/var/lib/mysql:rw"]),
            ("redis:7-alpine",6379,["--tmpfs","/data:rw"]),
        ):
            ident=docker("run","--pull=never","-d","--label",label,"--memory","768m","-p",f"127.0.0.1::{internal}",*extra,image)
            if len(ident)!=64 or any(c not in "0123456789abcdef" for c in ident):raise RuntimeError("Unexpected container identity")
            containers.append(ident)
        def published(ident,internal):return json.loads(docker("inspect","--format","{{json .NetworkSettings.Ports}}",ident))[f"{internal}/tcp"][0]["HostPort"]
        mysql_port=published(containers[0],3306);redis_port=published(containers[1],6379)
        import pymysql
        for _ in range(90):
            try:
                with pymysql.connect(host="127.0.0.1",port=int(mysql_port),user="root",database="steel_lab_test_pcb",connect_timeout=2):break
            except pymysql.Error:time.sleep(1)
        else:raise RuntimeError("Temporary MySQL readiness")
        with tempfile.TemporaryDirectory(prefix="steel-pcb-batch-live-") as temp:
            cfg={"mysql_dsn":f"mysql+pymysql://root@127.0.0.1:{mysql_port}/steel_lab_test_pcb?charset=utf8mb4",
                 "redis_queue_url":f"redis://127.0.0.1:{redis_port}/0","redis_cache_url":f"redis://127.0.0.1:{redis_port}/1",
                 "storage_root":str(Path(temp)/"private-storage"),"rq_queue_name":"pcb_batch_acceptance"}
            config=Path(temp)/"runtime.json";config.write_text(json.dumps(cfg),encoding="utf-8")
            settings=bootstrap(config)
            from app.db.session import Base,engine as dbengine,SessionLocal
            from app.db.models import User,Session as AuthSession,Task,TaskModel,Artifact,MetricSet,AuditLog
            from app.util_time import new_id,utcnow
            from app.cache import rq_connection
            from rq import Worker,Queue
            from rq.job import Job
            from PIL import Image
            import numpy as np
            import httpx
            engine=dbengine;Base.metadata.create_all(engine)
            tokens={}
            with SessionLocal() as db:
                check(db.query(User).count()==0,"fresh isolated database")
                for role in ("owner","peer","advisor"):
                    user=User(id=new_id(),username="PCB批量验收_"+role,password_hash="unused-synthetic",role="advisor" if role=="advisor" else "student",status="active")
                    db.add(user);db.flush();tokens[role]=new_id()
                    db.add(AuthSession(id=tokens[role],user_id=user.id,expires_at=utcnow()+timedelta(hours=1)))
                db.commit()
            def spawn(mode,suffix="",listen_port=None):
                log=(out/(mode[2:]+suffix+".log")).open("w",encoding="utf-8");logs.append(log)
                args=[sys.executable,"-B",__file__,mode,str(config)]+([str(listen_port)] if listen_port else [])
                process=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=log,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(process);return process
            api_port=port();api=spawn("--api",listen_port=api_port);worker=spawn("--worker")
            origin=f"http://127.0.0.1:{api_port}"
            with httpx.Client(base_url=origin,timeout=60,trust_env=False) as http:
                for _ in range(120):
                    if api.poll() is not None:raise RuntimeError("Owned API exited")
                    try:
                        if http.get("/api/scenes/pcb/segmentation/models").status_code==401:break
                    except httpx.HTTPError:pass
                    time.sleep(1)
                else:raise RuntimeError("API readiness")
                for _ in range(180):
                    if worker.poll() is not None:raise RuntimeError("Owned Worker exited")
                    if any(w.get_state()=="idle" for w in Worker.all(connection=rq_connection())):break
                    time.sleep(1)
                else:raise RuntimeError("Worker readiness")
                images=[];arrays=[]
                for name,width,height in (("native.png",220,220),("wide.png",512,384)):
                    yy,xx=np.indices((height,width));a=np.stack([(xx*3+yy*5)%256,(xx+yy*7)%256,(xx*11+yy)%256],axis=-1).astype(np.uint8)
                    arrays.append(a);buf=io.BytesIO();Image.fromarray(a).save(buf,format="PNG")
                    images.append({"name":name,"base64":base64.b64encode(buf.getvalue()).decode(),"width":width,"height":height})
                gt=np.zeros((220,220),np.uint8);gt[40:90,60:100]=255
                buf=io.BytesIO();Image.fromarray(gt).save(buf,format="PNG")
                payload={"apiBase":origin,"tokens":tokens,"output":str(out),"images":images,"gt":{"name":"native_mask.png","base64":base64.b64encode(buf.getvalue()).decode()}}
                pw=Path(os.environ["USERPROFILE"])/".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
                print("Owned API/Worker ready; starting real batch browser",flush=True)
                browser=subprocess.run(["node","tests/check_pcb_batch_browser.mjs",str(pw)],input=json.dumps(payload),capture_output=True,text=True,encoding="utf-8",cwd=ROOT,env=env,timeout=900)
                # Browser promises not to print ephemeral sessions; redact defensively.
                browser_log=browser.stdout+browser.stderr
                for token in tokens.values():browser_log=browser_log.replace(token,"[redacted]")
                (out/"browser.log").write_text(browser_log,encoding="utf-8")
                check(browser.returncode==0,"real browser batch acceptance")
                ui=json.loads((out/"browser-results.json").read_text(encoding="utf-8"))
                batch_id=ui["batch_id"];ids=ui["task_ids"]
                check(len(ids)==len(set(ids))==6,"two images times three independent tasks")
                report["batch_id"]=batch_id;report["tasks"]=[]
                def auth(role="owner"):
                    http.cookies.clear();http.cookies.set("lab_session",tokens[role])
                auth()
                details={}
                with SessionLocal() as db:
                    for ident in ids:
                        data=http.get(f"/api/tasks/{ident}").json();details[ident]=data
                        task=db.get(Task,ident)
                        check(task.status=="success" and task.type=="pcb_segmentation","durable PCB success "+ident)
                        check(db.query(TaskModel).filter_by(task_id=ident).count()==1,"single model per child "+ident)
                        check(db.query(MetricSet).filter_by(task_id=ident).count()==int(task.has_gt),"GT-only metrics "+ident)
                        check(db.query(AuditLog).filter_by(target_id=ident,action="pcb.finish").count()==1,"single finish audit "+ident)
                        check(Job.fetch("task-"+ident,connection=rq_connection()).is_finished,"RQ finished "+ident)
                        expected=(220,220) if task.has_gt else (512,384)
                        check(data['metrics']['available'] is task.has_gt,'detail GT availability '+ident)
                        check(data["cam"]["status"] in {"ok","unavailable","failed"} if task.has_gt else data["cam"]["status"]=="not_supported_for_size","CAM capability truthful "+ident)
                        downloaded={}
                        for artifact in data["artifacts"]:
                            response=http.get(artifact["url"]);check(response.status_code==200,"authorized artifact "+artifact["kind"]+ident)
                            if artifact["rel_path"].endswith(".png"):
                                with Image.open(io.BytesIO(response.content)) as decoded:
                                    check(decoded.size==expected,"full-resolution artifact "+artifact["kind"]+ident)
                                    downloaded[artifact['kind']]=np.asarray(decoded).copy()
                                    if artifact["kind"]=="origin":check(np.array_equal(np.asarray(decoded),arrays[0 if task.has_gt else 1]),"origin pixels preserved "+ident)
                        if task.has_gt:
                            prediction=downloaded['pred_mask']==1;truth=downloaded['gt']==1
                            values={'tp':int((prediction&truth).sum()),'fp':int((prediction&~truth).sum()),
                                    'fn':int((~prediction&truth).sum()),'tn':int((~prediction&~truth).sum())}
                            check(all(data['metrics'][key]==value for key,value in values.items()),'downloaded pixels reproduce confusion counts '+ident)
                        report["tasks"].append({"id":ident,"model":data["model"]["id"],"size":list(expected),"status":task.status,"has_gt":task.has_gt,"cam":data["cam"]})
                group_url=f"/api/scenes/pcb/segmentation/batches/{batch_id}"
                group=http.get(group_url).json();check(group["counts"]["success"]==6,"persisted complete aggregate")
                check(len(group['samples'])==2,'exactly two source samples')
                for source in group['samples']:
                    check(len(source['tasks'])==3 and {t['model']['id'] for t in source['tasks']}=={'unet','unet_resnet18','unetpp_resnet18'},'each source has all three models '+source['client_file_id'])
                check(sum(t['has_gt'] for t in details.values())==3,'only one source has GT across three models')
                first=ids[0];file_url=f"/api/tasks/{first}/file/origin/image.png"
                for role in ("peer","advisor"):
                    auth(role);check(http.get(group_url).status_code==404,role+" cannot read private group")
                    check(http.get(file_url).status_code==404,role+" cannot read private image")
                auth();check(http.post(f"/api/records/{first}/submit").status_code==200,"submit one child")
                auth("advisor");visible=http.get(group_url).json()
                check(visible["counts"]["total"]==1 and [t["id"] for s in visible["samples"] for t in s["tasks"]]==[first],"advisor sees only submitted child and matching sample")
                check(http.get(file_url).status_code==200,"submitted preview visible")
                auth();check(http.post(f"/api/records/{first}/withdraw").status_code==200,"withdraw child")
                auth("advisor");check(http.get(group_url).status_code==404 and http.get(file_url).status_code==404,"withdraw revokes group and image")
                http.cookies.clear();check(http.get(group_url).status_code==401,"guest group denied");auth()
                # No task mutation: invalid attempts must fail before creating jobs.
                for rel in ("inputs.json","task.json","model.pth","../inputs.json","origin/%252e%252e/inputs.json"):
                    check(http.get(f"/api/tasks/{first}/file/{rel}").status_code in (400,404),"private path denied "+rel)
                for size in (1,2,50):
                    page=http.get(group_url,params={"page":1,"page_size":size}).json()
                    check(sum(len(s["tasks"]) for s in page["samples"])<=size,"server pagination "+str(size))
                # Actual overlapping requests, with Worker paused so queue multiplicity is observable.
                stop(worker)
                manifest={'files':[{'client_file_id':'concurrent','file_field':'image'}]}
                uploaded=http.post('/api/scenes/pcb/segmentation/uploads/batch',data={'manifest':json.dumps(manifest)},
                    files={'image':('roi.png',base64.b64decode(images[0]['base64']),'image/png')})
                check(uploaded.status_code==200,'concurrent fixture upload')
                concurrent_id=uploaded.json()['batch_id']
                body={'batch_id':concurrent_id,'model_ids':['unet','unet_resnet18','unetpp_resnet18'],
                      'include_cam':False,'accept_unsupported_cam':False}
                gate=threading.Barrier(2)
                def concurrent_request(_):
                    with httpx.Client(base_url=origin,timeout=120,trust_env=False,cookies={'lab_session':tokens['owner']}) as caller:
                        gate.wait(timeout=10)
                        response=caller.post('/api/scenes/pcb/segmentation/tasks/batch',json=body,headers={'Idempotency-Key':'concurrent-real'})
                        return response.status_code,response.json()
                with ThreadPoolExecutor(max_workers=2) as executor:responses=list(executor.map(concurrent_request,range(2)))
                check(all(code==200 for code,_ in responses),'simultaneous same-key submissions both succeed')
                sets=[{t['id'] for s in data['samples'] for t in s['tasks']} for _,data in responses]
                check(sets[0]==sets[1] and len(sets[0])==3,'concurrent requests return identical three children')
                queue=Queue(settings.rq_queue_name,connection=rq_connection())
                check(sorted(queue.get_job_ids())==sorted('task-'+ident for ident in sets[0]),'concurrent requests enqueue each job once')
                # The deliberately stopped fixed-name worker retains its RQ
                # registration until TTL expiry. Drain only this isolated queue
                # with the existing unique-name burst runner; never clear keys.
                worker=spawn('--burst',suffix='-concurrent')
                for _ in range(180):
                    current=http.get(f'/api/scenes/pcb/segmentation/batches/{concurrent_id}').json()
                    if current['counts']['success']==3:break
                    if current['counts']['failed']:raise AssertionError('concurrency tasks failed')
                    if worker.poll() is not None:raise RuntimeError('concurrency worker exited before completion')
                    time.sleep(1)
                else:raise RuntimeError('concurrency tasks timeout')
                report['concurrency']={'status':'PASS','batch_id':concurrent_id,'task_ids':sorted(sets[0])}
                check(Queue(settings.rq_queue_name,connection=rq_connection()).count==0,"no pending batch jobs")
                report["status"]="PASS"
            for process in reversed(processes):stop(process)
            engine.dispose();engine=None
    except Exception as exc:
        report["status"]="FAIL"
        report["error_type"]=type(exc).__name__
        raise
    finally:
        failures=[]
        for process in reversed(processes):
            try:stop(process)
            except Exception as exc:failures.append(type(exc).__name__)
        for log in logs:log.close()
        if engine is not None:engine.dispose()
        for ident in reversed(containers):
            try:
                labels=json.loads(docker("inspect","--format","{{json .Config.Labels}}",ident));key,value=label.split("=",1)
                if labels.get(key)!=value:raise RuntimeError("Container label changed")
                docker("rm","-f",ident)
            except Exception as exc:failures.append(type(exc).__name__)
        report["cleanup"]="PASS" if not failures else failures
        if failures:report["status"]="FAIL"
        (out/"live-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if report["status"]!="PASS":raise RuntimeError("Acceptance incomplete")
    print("PASS batch live: "+str(len(report["assertions"]))+" assertions",flush=True)


if __name__=="__main__":main()
