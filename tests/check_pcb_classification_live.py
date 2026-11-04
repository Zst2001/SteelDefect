"""Real isolated MySQL/Redis/RQ/HTTP/browser admission. No daily .env/services.

Uses existing PCB isolation bootstrap, cached Docker images and actual Worker
entry point. Fault modes are explicit synthetic injection in owned child
processes, never production hooks. A fresh --output preserves earlier evidence.
"""
import argparse
import base64
import hashlib
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from check_pcb_infrastructure import ROOT, bootstrap, docker


def stop(process):
    if process.poll() is None:
        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        process.wait(timeout=15)


def child(mode, config, port=None):
    settings=bootstrap(config)
    if mode=="--api":
        import uvicorn
        from app.main import app
        uvicorn.run(app,host="127.0.0.1",port=int(port),log_level="warning")
        return
    if mode=="--worker":
        from apps.worker.__main__ import main
        main()
        return
    from apps.worker import jobs, pcb_classification
    from app.cache import rq_connection
    from rq import Queue, SimpleWorker
    if mode=="--burst-timeout":
        def timeout(*args):
            from rq.timeouts import JobTimeoutException
            raise JobTimeoutException("synthetic deadline injection in isolated RQ")
        pcb_classification.compute=timeout
    if mode=="--burst-start-failure":
        def fail(*args): raise ImportError("synthetic preclaim dependency failure")
        jobs.run_pcb_classification=fail
    connection=rq_connection()
    SimpleWorker([Queue(settings.rq_queue_name,connection=connection)],connection=connection,
                 name="roi-burst-"+uuid.uuid4().hex[:8]).work(burst=True,with_scheduler=False,logging_level="WARNING")


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));return sock.getsockname()[1]


def main():
    if len(sys.argv)>1 and sys.argv[1].startswith("--") and sys.argv[1]!="--output":
        child(*sys.argv[1:]);return
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists(): raise RuntimeError("Evidence directory must be fresh")
    out.mkdir(parents=True)
    owned=[];processes=[];logs=[];label="steel.roi.acceptance="+uuid.uuid4().hex
    report={"status":"RUNNING","scope":"isolated MySQL/Redis/RQ + Windows CPU + live HTTP/browser","checks":[],"negative_tasks":[]}
    def check(ok,message):
        assert ok,message
        report["checks"].append(message)
    env={**os.environ,"PYTHONIOENCODING":"utf-8","PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1"}
    engine=None
    try:
        for image,internal,extra in (
            ("mysql:8.0",3306,["--env","MYSQL_ALLOW_EMPTY_PASSWORD=yes","--env","MYSQL_DATABASE=steel_lab_test_pcb","--tmpfs","/var/lib/mysql:rw"]),
            ("redis:7-alpine",6379,["--tmpfs","/data:rw"]),
        ):
            ident=docker("run","--pull=never","-d","--label",label,"--memory","768m","-p",f"127.0.0.1::{internal}",*extra,image)
            assert len(ident)==64 and all(c in "0123456789abcdef" for c in ident);owned.append(ident)
        mysql_port=json.loads(docker("inspect","--format","{{json .NetworkSettings.Ports}}",owned[0]))["3306/tcp"][0]["HostPort"]
        redis_port=json.loads(docker("inspect","--format","{{json .NetworkSettings.Ports}}",owned[1]))["6379/tcp"][0]["HostPort"]
        import pymysql
        for _ in range(90):
            try:
                with pymysql.connect(host="127.0.0.1",port=int(mysql_port),user="root",database="steel_lab_test_pcb",connect_timeout=2):break
            except pymysql.Error:time.sleep(1)
        else:raise RuntimeError("isolated MySQL unavailable")
        with tempfile.TemporaryDirectory(prefix="steel-roi-live-") as temp:
            cfg={"mysql_dsn":f"mysql+pymysql://root@127.0.0.1:{mysql_port}/steel_lab_test_pcb?charset=utf8mb4",
                 "redis_queue_url":f"redis://127.0.0.1:{redis_port}/0","redis_cache_url":f"redis://127.0.0.1:{redis_port}/1",
                 "storage_root":str(Path(temp)/"private-storage"),"rq_queue_name":"roi_acceptance","pcb_classification_enabled":True}
            config=Path(temp)/"runtime.json";config.write_text(json.dumps(cfg),encoding="utf-8")
            settings=bootstrap(config)
            from app.db.session import Base, engine as dbengine, SessionLocal
            engine=dbengine
            from app.db.models import User, Session as AuthSession, Task, Sample, Artifact, MetricSet, AuditLog, TaskModel
            from app.util_time import new_id, utcnow
            from app.cache import rq_connection
            from rq import Queue, Worker
            from rq.job import Job
            from infer.pcb_classification.catalog import admitted
            admitted(ROOT/"assets/pcb_classification/deeppcb_roi_v0_formal_v1")
            Base.metadata.create_all(engine)
            tokens={};user_ids={}
            with SessionLocal() as db:
                assert db.query(User).count()==0
                for role in ("owner","peer","advisor","disabled_owner"):
                    user=User(id=new_id(),username="ROI验收_"+role,password_hash="unused-test-fixture",role="advisor" if role=="advisor" else "student",status="active")
                    db.add(user);db.flush();token=new_id();tokens[role]=token;user_ids[role]=user.id
                    db.add(AuthSession(id=token,user_id=user.id,expires_at=utcnow()+timedelta(hours=1)))
                db.commit()
            def spawn(mode, configuration=config, listen_port=None, suffix=""):
                log=(out/(mode[2:]+suffix+".log")).open("w",encoding="utf-8");logs.append(log)
                args=[sys.executable,"-B",__file__,mode,str(configuration)]+([str(listen_port)] if listen_port else [])
                process=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=log,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(process);return process
            api_port=port();api=spawn("--api",listen_port=api_port);worker=spawn("--worker")
            import httpx
            api_base=f"http://127.0.0.1:{api_port}"
            with httpx.Client(base_url=api_base,timeout=30,trust_env=False) as http:
                for _ in range(120):
                    if api.poll() is not None:raise RuntimeError("API exited; see owned api.log")
                    try:
                        if http.get("/api/scenes/pcb/classification/models").status_code==401:break
                    except httpx.HTTPError:pass
                    time.sleep(1)
                else:raise RuntimeError("API readiness timeout")
                for _ in range(180):
                    if worker.poll() is not None:raise RuntimeError("Worker exited; see owned worker.log")
                    if any(w.name=="lab-worker" and w.get_state()=="idle" for w in Worker.all(connection=rq_connection())):break
                    time.sleep(1)
                else:raise RuntimeError("Worker readiness timeout")
                print("Real isolated API/Worker ready; running browser",flush=True)
                from PIL import Image
                import numpy as np
                yy,xx=np.indices((224,224));gray=Image.fromarray(((xx*3+yy*5+17)%256).astype(np.uint8))
                png=io.BytesIO();gray.save(png,format="PNG");jpeg=io.BytesIO();gray.convert("RGB").resize((180,150)).save(jpeg,format="JPEG")
                pw=Path(os.environ["USERPROFILE"])/".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
                payload={"apiBase":api_base,"tokens":tokens,"output":str(out),"png":base64.b64encode(png.getvalue()).decode(),"jpeg":base64.b64encode(jpeg.getvalue()).decode()}
                browser=subprocess.run(["node","tests/check_pcb_classification_browser.mjs",str(pw)],cwd=ROOT,
                    input=json.dumps(payload),capture_output=True,text=True,encoding="utf-8",env=env,timeout=480)
                (out/"browser.log").write_text(browser.stdout+browser.stderr,encoding="utf-8")
                check(browser.returncode==0,"real browser two-model acceptance")
                ui=json.loads((out/"browser-results.json").read_text(encoding="utf-8"));report["runs"]=ui["runs"]
                print(browser.stdout,flush=True)
                def auth(role="owner"):
                    http.cookies.clear();http.cookies.set("lab_session",tokens[role])
                auth();first=ui["runs"][0]["taskId"];url=f"/api/tasks/{first}/file/pcb_classification.json"
                preview_url=f"/api/tasks/{first}/file/origin/image.png"
                for run in ui["runs"]:
                    preview=http.get(f"/api/tasks/{run['taskId']}/file/origin/image.png")
                    check(preview.status_code==200,"owner preview download "+run["taskId"])
                    with Image.open(io.BytesIO(preview.content)) as decoded:
                        check(decoded.mode=="L" and decoded.size==(224,224),"stored grayscale preview "+run["taskId"])
                        if not run["adapted"]:
                            check(np.array_equal(np.asarray(decoded),np.asarray(gray)),"native PNG pixels unchanged "+run["taskId"])
                with SessionLocal() as db:
                    for run in ui["runs"]:
                        ident=run["taskId"]
                        check(db.get(Task,ident).status=="success","durable success "+ident)
                        check(db.query(Artifact).filter_by(task_id=ident).count()==2,"two private artifacts "+ident)
                        check(db.query(MetricSet).filter_by(task_id=ident).count()==0,"no MetricSet "+ident)
                        check(db.query(AuditLog).filter_by(target_id=ident,action="pcb_cls.finish").count()==1,"finish audit "+ident)
                        check(Job.fetch("task-"+ident,connection=rq_connection()).is_finished,"RQ finished "+ident)
                    firsttask=db.get(Task,first);batch_id=firsttask.dataset_version_id
                for role in ("peer","advisor"):
                    auth(role)
                    check(http.get(f"/api/tasks/{first}").status_code==404,role+" cannot read private task")
                    check(http.get(url).status_code==404,role+" cannot download private JSON")
                    check(http.get(preview_url).status_code==404,role+" cannot download private preview")
                    check(http.post("/api/scenes/pcb/classification/tasks",json={"batch_id":batch_id,"model_id":"efficientnet_b0"}).status_code==404,role+" cannot reuse private ROI")
                http.cookies.clear();check(http.get(url).status_code==401,"guest cannot download")
                check(http.get(preview_url).status_code==401,"guest cannot download preview")
                auth();check(http.post(f"/api/records/{first}/submit").status_code==200,"explicit submit")
                auth("advisor");check(http.get(url).status_code==200,"submitted advisor download")
                check(http.get(preview_url).status_code==200,"submitted advisor preview")
                auth();check(http.post(f"/api/records/{first}/withdraw").status_code==200,"withdraw before seen")
                auth("advisor");check(http.get(url).status_code==404,"withdraw revokes download immediately")
                check(http.get(preview_url).status_code==404,"withdraw revokes preview immediately");auth()
                stop(worker)
                queue=Queue(settings.rq_queue_name,connection=rq_connection())
                def new_task(key,actor="owner"):
                    auth(actor)
                    response=http.post("/api/scenes/pcb/classification/uploads",files={"file":("roi.png",png.getvalue(),"image/png")})
                    check(response.status_code==200,"upload "+key);batch=response.json()["batch_id"]
                    body={"batch_id":batch,"model_id":"efficientnet_b0"}
                    before_jobs=queue.get_job_ids()
                    response=http.post("/api/scenes/pcb/classification/tasks",json=body,headers={"Idempotency-Key":key})
                    check(response.status_code==200,"queued "+key);task=response.json()["id"]
                    again=http.post("/api/scenes/pcb/classification/tasks",json=body,headers={"Idempotency-Key":key})
                    check(again.status_code==200 and again.json()["id"]==task,"idempotent "+key)
                    conflict=http.post("/api/scenes/pcb/classification/tasks",json={**body,"model_id":"mobilenet_v3_small"},headers={"Idempotency-Key":key})
                    check(conflict.status_code==409,"idempotency conflict "+key)
                    check(queue.get_job_ids()==before_jobs+["task-"+task],"one queued job after duplicate/conflicting requests "+key)
                    with SessionLocal() as db:
                        check(db.query(Task).filter_by(dataset_version_id=batch).count()==1,"one task after idempotent submission "+key)
                        check(db.query(TaskModel).filter_by(task_id=task).count()==1,"one model link after idempotent submission "+key)
                    return task,batch
                def burst(mode="--burst",configuration=config,suffix=""):
                    proc=spawn(mode,configuration,suffix=suffix)
                    check(proc.wait(timeout=180)==0,"real RQ burst exited "+mode+suffix)
                def failed(ident,code,stage):
                    with SessionLocal() as db:
                        task=db.get(Task,ident)
                        check(task.status=="failed" and code in task.error_summary,"terminal failure "+code)
                        check(db.query(Artifact).filter_by(task_id=ident).count()==0,"no failed artifacts "+code)
                        check(db.query(MetricSet).filter_by(task_id=ident).count()==0,"no failed MetricSet "+code)
                        check(len(task.models)==1,"exactly one failed TaskModel "+code)
                        link=task.models[0]
                        check(link.status=="failed" and link.fail_stage==stage and link.fail_message==task.error_summary,"TaskModel failure stage/message "+code)
                    check(Job.fetch("task-"+ident,connection=rq_connection()).is_failed,"RQ terminal failure "+code)
                    report["negative_tasks"].append({"id":ident,"code":code,"stage":stage,"status":"failed"})
                # Reuse the real records endpoint and the same isolated RQ path.
                original_result=http.get(url).content
                rerun=http.post(f"/api/records/{first}/rerun")
                check(rerun.status_code==200,"real history rerun accepted")
                rerun_id=rerun.json()["id"]
                check(rerun_id!=first and rerun.json()["type"]=="pcb_classify","rerun has new classification task identity")
                burst(suffix="-rerun")
                with SessionLocal() as db:
                    rerun_task=db.get(Task,rerun_id)
                    check(rerun_task.status=="success" and rerun_task.dataset_version_id==batch_id,"real rerun succeeds with frozen original batch")
                    check(db.query(Artifact).filter_by(task_id=rerun_id).count()==2,"rerun has two artifacts")
                    check(db.query(MetricSet).filter_by(task_id=rerun_id).count()==0,"rerun has no metrics")
                    check(db.query(AuditLog).filter_by(target_id=rerun_id,action="pcb_cls.finish").count()==1,"rerun finish audited once")
                check(Job.fetch("task-"+rerun_id,connection=rq_connection()).is_finished,"rerun RQ finished")
                redelivery="roi-redelivery-"+uuid.uuid4().hex
                queue.enqueue("apps.worker.jobs.run_pcb_classification",first,job_id=redelivery,job_timeout=settings.pcb_classification_job_timeout_sec)
                burst(suffix="-redelivery")
                check(Job.fetch(redelivery,connection=rq_connection()).is_finished,"successful task redelivery finishes without reexecution")
                with SessionLocal() as db:
                    check(db.get(Task,first).status=="success","redelivery preserves successful task status")
                    check(db.query(Artifact).filter_by(task_id=first).count()==2,"redelivery does not duplicate artifacts")
                    check(db.query(AuditLog).filter_by(target_id=first,action="pcb_cls.finish").count()==1,"redelivery does not repeat finish audit")
                check(http.get(url).content==original_result,"rerun and redelivery preserve original result bytes")
                report["lifecycle"]={"rerun_id":rerun_id,"redelivery_job_id":redelivery,"status":"PASS"}
                disabled_cfg=Path(temp)/"disabled.json";disabled_cfg.write_text(json.dumps({**cfg,"pcb_classification_enabled":False}),encoding="utf-8")
                flag,_=new_task("flag-disabled");burst(configuration=disabled_cfg,suffix="-disabled");failed(flag,"PCB_CLS_DISABLED","scene")
                actor,_=new_task("disabled-actor","disabled_owner")
                changed,changed_batch=new_task("bytes-changed")
                wrong,_=new_task("model-role-changed")
                from app.services.storage import resolve_uri
                with SessionLocal() as db:
                    db.get(User,user_ids["disabled_owner"]).status="disabled"
                    sample=db.query(Sample).filter_by(version_id=changed_batch).one()
                    resolve_uri(sample.origin_uri,settings).write_bytes(b"changed-in-isolated-storage")
                    db.query(TaskModel).filter_by(task_id=wrong).one().role="student_under_test"
                    db.commit()
                burst(suffix="-negatives")
                failed(actor,"TASK_ACTOR_UNAVAILABLE","auth");failed(changed,"INPUT_CHANGED","file");failed(wrong,"PCB_CLS_PROTOCOL_CHANGED","protocol")
                timeout,_=new_task("timeout");burst("--burst-timeout");failed(timeout,"PCB_CLS_JOB_TIMEOUT","resource")
                unclaimed,_=new_task("preclaim");burst("--burst-start-failure");failed(unclaimed,"PCB_CLS_JOB_START_FAILED","queue")
                auth()
                for filename,content,mime in [("roi.png",b"","image/png"),("roi.png",b"broken","image/png"),("../roi.png",png.getvalue(),"image/png")]:
                    check(http.post("/api/scenes/pcb/classification/uploads",files={"file":(filename,content,mime)}).status_code==400,"real HTTP invalid image "+filename+str(len(content)))
                detected=http.post("/api/scenes/pcb/classification/uploads",files={"file":("camera.jpg",png.getvalue(),"image/jpeg")})
                check(detected.status_code==200,"real HTTP trusts decoded image content over filename/MIME")
                detected=detected.json()
                check(detected["source_image"]["format"]=="PNG" and detected["source_image"]["sha256"]==hashlib.sha256(png.getvalue()).hexdigest(),"content-detected upload preserves original provenance")
                with SessionLocal() as db:
                    check(db.query(Task).filter_by(dataset_version_id=detected["batch_id"]).count()==0,"upload alone creates no model tasks")
                for model in ("unet","resnet18","../efficientnet_b0"):
                    check(http.post("/api/scenes/pcb/classification/tasks",json={"batch_id":batch_id,"model_id":model}).status_code==400,"unknown model "+model)
                for rel in ("inputs.json","task.json","model.pth","MANIFEST.json","../inputs.json","origin/%252e%252e/inputs.json"):
                    check(http.get(f"/api/tasks/{first}/file/{rel}").status_code in (400,404),"artifact denied "+rel)
                check(queue.count==0,"no stranded queued jobs")
                # Real HTTP gate off in a newly started, owned API, history remains readable.
                stop(api);disabled_port=port();disabled_api=spawn("--api",disabled_cfg,disabled_port,suffix="-disabled")
                with httpx.Client(base_url=f"http://127.0.0.1:{disabled_port}",timeout=30,trust_env=False) as off:
                    off.cookies.set("lab_session",tokens["owner"])
                    for _ in range(120):
                        try:
                            response=off.get("/api/scenes/pcb/classification/models")
                            if response.status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(1)
                    else:raise RuntimeError("disabled API readiness")
                    check(not response.json()["available"] and not response.json()["enabled"],"disabled catalog truthful")
                    check(off.post("/api/scenes/pcb/classification/tasks",json={"batch_id":batch_id,"model_id":"efficientnet_b0"}).status_code==409,"disabled API refuses new tasks")
                    check(off.get(url).status_code==200,"disabled API keeps authorized historical JSON readable")
            report["status"]="PASS"
            # Stop owned processes before their temporary storage is cleaned up.
            for process in reversed(processes):stop(process)
            engine.dispose();engine=None
    finally:
        for process in reversed(processes):stop(process)
        for log in logs:log.close()
        if engine is not None:engine.dispose()
        for ident in reversed(owned):
            actual=json.loads(docker("inspect","--format","{{json .Config.Labels}}",ident));key,value=label.split("=",1)
            if actual.get(key)==value:docker("rm","-f",ident)
        report["cleanup"]="owned processes and label-verified disposable containers removed"
        (out/"live-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PASS live acceptance: {len(report['checks'])} infrastructure/security assertions",flush=True)


if __name__=="__main__":main()
