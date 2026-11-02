"""Offline isolated API/permissions/publication tests, synthetic outputs only."""
import io
import sys
from types import SimpleNamespace
from unittest.mock import Mock

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use tests/run_phase_a_tests.py")

import numpy as np
import pytest
from PIL import Image
from rq.timeouts import JobTimeoutException
from app.db.models import Artifact, DatasetVersion, MetricSet, PreprocessSpecRow, Sample, Task, TaskModel, User, Weight
from app.errors import AppError
from app.routers import pcb_classification as router
from app.services import pcb_classification as service
from app.services.dispatch import Delivery
from app.services.records import rerun_record, submit_to_advisor, withdraw_from_advisor
from app.services.storage import resolve_uri
from apps.worker import jobs, pcb_classification as worker
from infer.pcb_classification.catalog import MODELS, PROTOCOL, runtime_identity
from infer.pcb_classification.images import decode
from test_phase_a_authorization import lab, client

CLASSES = [{"class_id": i, "label_en": en, "label_zh": zh} for i, (en, zh) in enumerate(
    zip(("open", "short", "mousebite", "spur", "copper", "pin-hole"), ("断路", "短路", "鼠咬", "毛刺", "余铜", "针孔")))]


def image(mode="L", size=(224, 224), fmt="PNG", **kwargs):
    stream = io.BytesIO()
    Image.new(mode, size, 80).save(stream, format=fmt, **kwargs)
    return stream.getvalue()


def fake_compute(root, slug, content, filename):
    gray, facts = decode(content, filename)
    stream = io.BytesIO()
    gray.save(stream, format="PNG")
    return {"protocol_id": PROTOCOL, "model_id": slug, **CLASSES[3], "confidence": .75,
            "probabilities": [.05, .05, .05, .75, .05, .05], **facts}, stream.getvalue()


@pytest.fixture
def roi(lab, monkeypatch):
    object.__setattr__(lab.settings, "pcb_classification_enabled", True)
    def asset(slug, settings):
        if slug not in MODELS:
            raise AppError("unknown", code="PCB_CLS_MODEL_UNSUPPORTED", stage="protocol", status_code=400)
        return {"model_id": slug, "weight_sha256": MODELS[slug][0], "source_hash": "c" * 64, "classes": CLASSES}
    monkeypatch.setattr(service, "asset", asset)
    monkeypatch.setattr(worker, "asset", asset)
    monkeypatch.setattr(service, "get_settings", lambda: lab.settings)
    for module in (service, worker):
        monkeypatch.setattr(module, "invalidate_after_write", lambda *a: None)
    monkeypatch.setattr(worker, "compute", fake_compute)
    queue = Mock(side_effect=lambda _s, _f, ident, _timeout, **kw: Delivery("confirmed", "task-" + ident))
    monkeypatch.setattr(service, "enqueue", queue)
    return SimpleNamespace(lab=lab, queue=queue)


def create(roi, slug="efficientnet_b0", key=None):
    lab = roi.lab
    batch = service.create_batch(lab.db, lab.owner, "roi.png", image(), "image/png", lab.settings)
    task = service.create_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_id=slug, idempotency_key=key, settings=lab.settings)
    return batch, task


@pytest.mark.parametrize("slug", list(MODELS))
def test_roi_complete_permissions_and_history(roi, slug):
    lab = roi.lab
    batch, task = create(roi, slug)
    jobs.run_pcb_classification(task.id)
    lab.db.expire_all()
    with client(lab, lab.owner) as http:
        data = http.get(f"/api/tasks/{task.id}").json()
        assert data["status"] == "success" and data["type"] == "pcb_classify"
        assert data["metrics"] == {"available": False} and data["result"]["confidence"] == .75
        assert len(data["artifacts"]) == 2
        assert all(http.get(a["url"]).status_code == 200 for a in data["artifacts"])
        assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == 0
        rows = http.get("/api/records?type=pcb_classify").json()["items"]
        row = next(r for r in rows if r["id"] == task.id)
        assert row["can_submit"] and row["can_rerun"] and not row["can_analyze"]
    for user in (lab.peer, lab.advisor):
        with client(lab, user) as http:
            assert http.get(f"/api/tasks/{task.id}").status_code == 404
            assert http.get(data["result_download_url"]).status_code == 404
    task = lab.db.get(Task, task.id)
    submit_to_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(data["result_download_url"]).status_code == 200
    withdraw_from_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(data["result_download_url"]).status_code == 404
    new = rerun_record(lab.db, lab.owner, task.id)
    assert new.id != task.id and new.type == "pcb_classify"
    jobs.run_pcb_classification(task.id)
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 2


@pytest.mark.parametrize("name,content,mime", [
    ("roi.png", b"", "image/png"), ("roi.png", b"x" * (2 * 1024 * 1024 + 1), "image/png"),
    ("roi.png", b"broken", "image/png"), ("roi.png", image(), "image/jpeg"),
    ("roi.jpg", image(), "image/jpeg"), ("../roi.png", image(), "image/png"),
    ("C:\\roi.png", image(), "image/png"), ("roi.png", image("I;16"), "image/png"),
    ("roi.png", image(size=(4097,4096)), "image/png"),
], ids=["empty","oversize-bytes","corrupt","mime","extension","traversal","absolute-path","16bit","oversize-pixels"])
def test_invalid_inputs_do_not_persist(roi, name, content, mime):
    lab = roi.lab
    before = lab.db.query(DatasetVersion).count()
    with pytest.raises(AppError):
        service.create_batch(lab.db, lab.owner, name, content, mime, lab.settings)
    assert lab.db.query(DatasetVersion).count() == before
    roi.queue.assert_not_called()


@pytest.mark.parametrize("mode,size,fmt,name", [("L",(224,224),"PNG","roi.png"), ("RGB",(100,180),"JPEG","roi.jpg"), ("L",(224,224),"JPEG","roi.jpg")])
def test_native_pixels_and_adaptation(mode,size,fmt,name):
    content = image(mode,size,fmt)
    gray, facts = decode(content,name,"image/png" if fmt == "PNG" else "image/jpeg")
    assert gray.size == (224,224) and gray.mode == "L"
    assert facts["input_adapted"] is (fmt != "PNG" or mode != "L" or size != (224,224))
    if not facts["input_adapted"]:
        assert np.array_equal(np.asarray(gray),np.asarray(Image.open(io.BytesIO(content))))


def test_exif_and_animation():
    exif=Image.Exif(); exif[274]=6
    with pytest.raises(ValueError): decode(image(exif=exif),"roi.png","image/png")
    stream=io.BytesIO()
    Image.new("L",(20,20),0).save(stream,format="PNG",save_all=True,append_images=[Image.new("L",(20,20),255)])
    with pytest.raises(ValueError): decode(stream.getvalue(),"roi.png","image/png")


def test_upload_contract_unknown_fields_and_ids(roi):
    lab=roi.lab
    with client(lab,lab.owner) as http:
        http.app.include_router(router.router,prefix="/api")
        for files in [ [("file",("roi.png",image(),"image/png"))]*2,
                       [("file",("roi.png",image(),"image/png")),("gt",("gt.png",image(),"image/png"))] ]:
            assert http.post("/api/scenes/pcb/classification/uploads",files=files).status_code==400
        for body in ({"batch_id":"x","model_id":"efficientnet_b0","path":"C:/file"}, {"batch_id":1,"model_id":"efficientnet_b0"}):
            assert http.post("/api/scenes/pcb/classification/tasks",json=body).status_code==422
    batch,task=create(roi,key="same")
    args={"batch_id":batch["batch_id"],"model_id":"efficientnet_b0","idempotency_key":"same","settings":lab.settings}
    assert service.create_task(lab.db,lab.owner,**args).id==task.id and roi.queue.call_count==1
    with pytest.raises(AppError): service.create_task(lab.db,lab.owner,**{**args,"model_id":"mobilenet_v3_small"})
    for slug in ("unet","mobilenet_v3_small.pth","../efficientnet_b0",lab.private.id):
        with pytest.raises(AppError): service.create_task(lab.db,lab.owner,**{**args,"model_id":slug})
    with pytest.raises(AppError): service.create_task(lab.db,lab.peer,**args)
    with pytest.raises(AppError): service.create_task(lab.db,lab.owner,**{**args,"batch_id":lab.batch.id})


@pytest.mark.parametrize("when", ["queued","publishing"])
@pytest.mark.parametrize("change", ["actor","flag","bytes","metadata","weight","admission"])
def test_revocation_prevents_outputs(roi, monkeypatch, when, change):
    lab=roi.lab
    batch,task=create(roi)
    def mutate():
        if change=="actor": lab.db.get(User,lab.owner.id).status="disabled"
        elif change=="flag": object.__setattr__(lab.settings,"pcb_classification_enabled",False)
        elif change=="bytes":
            row=lab.db.query(Sample).filter_by(version_id=batch["batch_id"]).one()
            resolve_uri(row.origin_uri,lab.settings).write_bytes(b"changed")
        elif change=="metadata":
            row=lab.db.get(DatasetVersion,batch["batch_id"]);row.class_map_json={**row.class_map_json,"filename":"changed.png"}
        elif change=="weight":
            mid=lab.db.query(TaskModel).filter_by(task_id=task.id).one().model_version_id
            lab.db.query(Weight).filter_by(version_id=mid).one().sha256="a"*64
        else:
            def unavailable(*a): raise AppError("asset unavailable",code="PCB_CLS_ASSET_UNAVAILABLE",stage="load")
            monkeypatch.setattr(worker,"asset",unavailable)
        lab.db.commit()
    if when=="queued": mutate()
    else:
        def compute(*args):
            result=fake_compute(*args);mutate();return result
        monkeypatch.setattr(worker,"compute",compute)
    with pytest.raises(AppError): jobs.run_pcb_classification(task.id)
    lab.db.expire_all()
    assert lab.db.get(Task,task.id).status=="failed"
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count()==0
    assert lab.db.query(MetricSet).filter_by(task_id=task.id).count()==0
    assert all(link.status=="failed" for link in lab.db.get(Task,task.id).models)


@pytest.mark.parametrize("during_claim",[True,False])
def test_timeout_reconciles_terminal_state(roi,monkeypatch,during_claim):
    _,task=create(roi)
    def timeout(*a): raise JobTimeoutException("synthetic deadline")
    monkeypatch.setattr(worker,"assert_execution" if during_claim else "compute",timeout)
    with pytest.raises(AppError,match="超过执行时限"): jobs.run_pcb_classification(task.id)
    roi.lab.db.expire_all()
    assert roi.lab.db.get(Task,task.id).status=="failed"
    assert all(link.fail_stage=="resource" for link in roi.lab.db.get(Task,task.id).models)


def test_whitelist_and_disable_preserve_history(roi):
    lab=roi.lab
    _,task=create(roi);jobs.run_pcb_classification(task.id);lab.db.expire_all()
    object.__setattr__(lab.settings,"pcb_classification_enabled",False)
    with client(lab,lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}").json()["status"]=="success"
        for path in ("inputs.json","task.json","model.pth","bundle.zip","MANIFEST.json","../inputs.json","origin/%2e%2e/inputs.json","PCB_CLASSIFICATION.JSON"):
            assert http.get(f"/api/tasks/{task.id}/file/{path}").status_code in (400,404)
        assert http.get(f"/api/tasks/{task.id}/file/pcb_classification.json").status_code==200
    with pytest.raises(AppError) as exc: rerun_record(lab.db,lab.owner,task.id)
    assert exc.value.code=="PCB_CLS_DISABLED"


@pytest.mark.parametrize("outcome",["rejected","unknown"])
def test_delivery_uncertainty_no_duplicate(roi,monkeypatch,outcome):
    monkeypatch.setattr(service,"enqueue",Mock(return_value=Delivery(outcome,"test-job")))
    _,task=create(roi,key="delivery")
    assert task.status in {"queued","failed"}
    assert task.error_summary


def test_probabilities_reject_nonfinite_and_shape():
    import torch
    from infer.pcb_classification.runtime import checked_output
    for logits in (torch.zeros(1,5),torch.full((1,6),float("nan")),torch.full((1,6),float("inf"))):
        with pytest.raises(ValueError): checked_output(logits,"efficientnet_b0",CLASSES,{})


def test_cache_binds_admission_and_preserves_single_capacity(tmp_path,monkeypatch):
    import torch
    from infer.pcb_classification import runtime
    runtime.clear_cache()
    state={"token":"a"}
    proof={"receipt":{"runtime":runtime_identity()},"configs":{"preprocess":{"mean":.5627062126943955,"std":.4855159641534125},"classes":{"classes":CLASSES}}}
    def admitted(_):
        if state["token"] is None: raise ValueError("stale")
        return {**proof,"token":state["token"]}
    monkeypatch.setattr(runtime,"admitted",admitted)
    monkeypatch.setattr(torch,"get_num_interop_threads",lambda:6)
    loads=Mock(side_effect=lambda *a: lambda x: torch.zeros(1,6))
    monkeypatch.setattr(runtime,"strict_load",loads)
    def predict(key="efficientnet_b0",**kw): return runtime.predict(tmp_path,key,image(),"roi.png",**kw)[0]
    assert not predict()["cache_hit"] and predict()["cache_hit"] and loads.call_count==1
    state["token"]="b"
    assert not predict()["cache_hit"] and loads.call_count==2
    assert not predict("mobilenet_v3_small")["cache_hit"] and not predict()["cache_hit"] and loads.call_count==4
    state["token"]=None
    with pytest.raises(ValueError): predict()
    assert runtime._cache is None
    with pytest.raises(ValueError): predict(enabled=False)


@pytest.mark.parametrize("postcheck", ["raises", "changed-token"])
def test_post_inference_admission_failure_drops_model(tmp_path,monkeypatch,postcheck):
    import torch
    from infer.pcb_classification import runtime
    runtime.clear_cache()
    proof={"token":"initial","receipt":{"runtime":runtime_identity()},"configs":{"preprocess":{"mean":.5,"std":.5},"classes":{"classes":CLASSES}}}
    outcomes=[proof, ValueError("receipt revoked") if postcheck=="raises" else {**proof,"token":"changed"}]
    monkeypatch.setattr(runtime,"admitted",Mock(side_effect=outcomes))
    monkeypatch.setattr(torch,"get_num_interop_threads",lambda:6)
    monkeypatch.setattr(runtime,"strict_load",lambda *args:lambda x:torch.zeros(1,6))
    with pytest.raises(ValueError):runtime.predict(tmp_path,"efficientnet_b0",image(),"roi.png")
    assert runtime._cache is None


def test_loaded_binary_version_must_match_receipt(tmp_path,monkeypatch):
    import torch
    from infer.pcb_classification import runtime
    proof={"receipt":{"runtime":runtime_identity()}}
    monkeypatch.setattr(runtime,"admitted",lambda _:proof)
    monkeypatch.setattr(torch,"__version__","outdated-resident-library")
    loads=Mock()
    monkeypatch.setattr(runtime,"strict_load",loads)
    with pytest.raises(ValueError,match="loaded libraries differ"):
        runtime.predict(tmp_path,"efficientnet_b0",image(),"roi.png")
    assert runtime._cache is None
    loads.assert_not_called()
