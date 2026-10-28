"""Opt-in, destructive-to-TEST-DATA-only MySQL RR acceptance (no schema DDL).

Requires an explicitly authorized, EMPTY, pre-provisioned InnoDB schema named
steel_lab_test_*. Never reads .env; password is prompted, never a CLI argument.
Does not drop tables/delete rows. Synthetic rows remain for inspection; use a fresh
disposable test schema for each run. All queues, Docker and other services are fake.
Example (ONLY after the owner authorizes the isolated instance):
  python -B tests/run_phase_c_mysql_checks.py --database steel_lab_test_c_repair \
    --user steel_test --port 13306 --confirm-isolated-test-db
Without confirmation this exits before importing the application or connecting.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


def build_suite(engine, settings):
    from sqlalchemy import event, select
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import sessionmaker
    from starlette.datastructures import UploadFile
    from PIL import Image
    from app.db.models import (User, PreprocessSpecRow, Dataset, DatasetVersion, Sample,
        Model, ModelVersion, Weight, Task, TaskModel, TaskSample, ModelPerfProfile)
    from app.errors import AppError
    from app.services import tasks, demo, import_model, perf, input_freeze, submission
    from app.services.demo_identity import DemoIdentity
    from app.services.dispatch import Delivery
    from app.routers import uploads
    from app.util_time import new_id
    from infer.spec import DEMO_CATALOG_KIND

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    source, weights = b"def build_model():\n    return None\n", b"synthetic-never-loaded"

    class Cases(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            with factory() as db:
                spec = PreprocessSpecRow(id=new_id(), name="neu_200", height=200, width=200,
                    apply_clahe=False, sp_threshold=.02, dataset="neu")
                db.add(spec)
                db.commit()
                cls.spec_id = spec.id

        def setUp(self):
            self.queue = Mock(return_value=Delivery("confirmed", "synthetic-job"))
            for module in (tasks, demo, import_model, perf, uploads):
                if hasattr(module, "get_settings"):
                    self.enterContext(patch.object(module, "get_settings", lambda: settings))
                if hasattr(module, "invalidate_after_write"):
                    self.enterContext(patch.object(module, "invalidate_after_write", lambda *a: None))
            for module, name in ((tasks, "_enqueue_task"), (demo, "_enqueue_task"),
                                 (import_model, "enqueue_admit"), (perf, "enqueue_perf")):
                self.enterContext(patch.object(module, name, self.queue))
            self.enterContext(patch.object(perf, "invalidate_models_lists", lambda: None))
            with factory() as db:
                user = User(id=new_id(), username=new_id(), password_hash="synthetic-unused", role="student", status="active")
                db.add(user)
                db.flush()
                dataset = Dataset(id=new_id(), owner_id=user.id, name="synthetic", visibility="private")
                model = Model(id=new_id(), owner_id=None, name="synthetic-builtin", source="builtin")
                db.add_all([dataset, model])
                db.flush()
                batch = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind="upload_batch",
                    preprocess_id=self.spec_id, is_fixed_test=False, forbid_student_gt_download=False)
                version = ModelVersion(id=new_id(), model_id=model.id, slug="unet", entry_symbol="build_model",
                    num_classes=4, in_channels=3, input_h=200, input_w=200, preprocess_id=self.spec_id,
                    requires_cuda=False, status="runnable", visibility="public")
                db.add_all([batch, version])
                db.flush()
                origin = settings.storage_path / f"{batch.id}.png"
                origin.parent.mkdir(parents=True, exist_ok=True)
                origin.write_bytes(b"synthetic-origin")
                sample = Sample(id=new_id(), version_id=batch.id, sample_key="s0", origin_uri=f"data:{origin.name}",
                    mask_uri=None, width=200, height=200, sha256=hashlib.sha256(origin.read_bytes()).hexdigest())
                db.add(sample)
                db.commit()
                self.user_id, self.batch_id, self.model_id, self.sample_id = user.id, batch.id, version.id, sample.id

        def race(self, parent, parent_id, first, second, prime=None):
            """A holds parent; B creates RR snapshot then demonstrably waits on its lock."""
            attempted, finished = threading.Event(), threading.Event()
            results, failures = [], []
            with factory() as a:
                a.query(parent).filter_by(id=parent_id).with_for_update().one()
                def contender():
                    try:
                        with factory() as b:
                            self.assertEqual(b.connection().get_isolation_level(), "REPEATABLE READ")
                            b.execute(select(User.id)).all()  # Establish snapshot BEFORE A commits.
                            if prime: prime(b)
                            connection = b.connection()
                            def before(conn, cursor, statement, parameters, context, many):
                                if "FOR UPDATE" in statement.upper() and parent.__tablename__ in statement:
                                    attempted.set()
                            event.listen(connection, "before_cursor_execute", before)
                            try:
                                results.append(second(b))
                                b.commit()
                            finally:
                                event.remove(connection, "before_cursor_execute", before)
                    except BaseException as exc:
                        failures.append(exc)
                    finally:
                        finished.set()
                worker = threading.Thread(target=contender, daemon=True)
                worker.start()
                try:
                    self.assertTrue(attempted.wait(10), "second connection never attempted parent lock")
                    self.assertFalse(finished.wait(.2), "second connection did not wait for parent lock")
                    first_result = first(a)
                    a.commit()
                finally:
                    a.rollback()  # Also releases the parent if the first operation/assertion fails.
                    worker.join(30)
                self.assertFalse(worker.is_alive(), "bounded race did not finish")
                if failures: raise failures[0]
                self.assertEqual(len(results), 1)
                return first_result, results[0]

        def import_one(self, db, content=source, weight_content=weights, classes=4):
            return asyncio.run(import_model.import_student_model(db, db.get(User, self.user_id),
                name="synthetic-import", entry_symbol="build_model", num_classes=classes, in_channels=3,
                requires_cuda=False, py_file=UploadFile(io.BytesIO(content), filename="model.py"),
                pth_file=UploadFile(io.BytesIO(weight_content), filename="weights.pth"),
                settings=settings, idempotency_key="same")).id

        def import_race(self, changed):
            def second(db):
                try:
                    return self.import_one(db, **changed)
                except AppError as exc:
                    self.assertEqual((exc.code, exc.status_code), ("IDEMPOTENCY_CONFLICT", 409))
                    return "conflict"
            first, other = self.race(User, self.user_id, self.import_one, second,
                prime=lambda db: db.query(PreprocessSpecRow).all())
            self.assertEqual(other, "conflict" if changed else first)
            root = import_model.model_dir(settings, first)
            self.assertEqual((root / "model.py").read_bytes(), source)
            self.assertEqual((root / "weights.pth").read_bytes(), weights)
            with factory() as db:
                self.assertEqual(db.query(ModelVersion).filter_by(id=first).count(), 1)
                self.assertEqual(db.get(ModelVersion, first).source_sha256, hashlib.sha256(source).hexdigest())
                self.assertEqual(db.query(Weight).filter_by(version_id=first).one().sha256, hashlib.sha256(weights).hexdigest())
            self.assertEqual(self.queue.call_count, 1)

        def test_import_same(self): self.import_race({})
        def test_import_source_conflict(self): self.import_race({"content": source + b"# different\n"})
        def test_import_weight_conflict(self): self.import_race({"weight_content": b"different"})
        def test_import_parameter_conflict(self): self.import_race({"classes": 3})

        def submit(self, db, kind="compare"):
            user = db.get(User, self.user_id)
            args = dict(baseline_version_ids=[self.model_id], settings=settings, idempotency_key="same")
            if kind == "demo":
                return demo.create_demo_task(db, DemoIdentity("synthetic", user, "test", "test"), sample_keys=["s0"], **args).id
            return getattr(tasks, f"create_{kind}_task")(db, user, student_version_id=None,
                **{("batch_id" if kind == "compare" else "dataset_version_id"): self.batch_id}, **args).id

        def task_race(self, kind):
            if kind != "compare":
                with factory() as db:
                    batch = db.get(DatasetVersion, self.batch_id)
                    batch.kind = DEMO_CATALOG_KIND if kind == "demo" else "preset"
                    if kind == "eval":
                        batch.is_fixed_test = batch.forbid_student_gt_download = True
                        first = db.get(Sample, self.sample_id)
                        mask = settings.storage_path / f"{self.batch_id}-mask.png"
                        mask.write_bytes(b"synthetic-mask")
                        first.mask_uri = f"data:{mask.name}"
                        for i in range(1, 20):
                            db.add(Sample(id=new_id(), version_id=self.batch_id, sample_key=f"s{i}",
                                origin_uri=first.origin_uri, mask_uri=first.mask_uri, sha256=first.sha256, width=200, height=200))
                    db.commit()
            def prime(db):
                db.query(Task).all(); db.query(TaskModel).all(); db.query(TaskSample).all(); db.query(Sample).all()
            first, second = self.race(User, self.user_id, lambda db: self.submit(db, kind),
                                     lambda db: self.submit(db, kind), prime)
            self.assertEqual(first, second)
            with factory() as db:
                self.assertEqual(db.query(Task).filter_by(creator_id=self.user_id).count(), 1)
                self.assertEqual(db.query(TaskModel).filter_by(task_id=first).count(), 1)
                self.assertEqual(db.query(TaskSample).filter_by(task_id=first).count(), 20 if kind == "eval" else 1)
            self.assertEqual(self.queue.call_count, 1)

        def test_compare_same(self): self.task_race("compare")
        def test_eval_same(self): self.task_race("eval")
        def test_demo_same(self): self.task_race("demo")

        def upload_mask(self, db):
            data = io.BytesIO()
            Image.new("L", (200, 200), color=1).save(data, format="PNG")
            return asyncio.run(uploads.upload_masks(batch_id=self.batch_id,
                files=[UploadFile(io.BytesIO(data.getvalue()), filename="s0.png")],
                user=db.get(User, self.user_id), db=db))

        def test_mask_first_task_reads_new_uri_and_hash(self):
            _, task_id = self.race(DatasetVersion, self.batch_id, self.upload_mask, self.submit,
                prime=lambda db: db.get(Sample, self.sample_id))
            with factory() as db:
                sample = db.get(Sample, self.sample_id)
                manifest = json.loads(input_freeze.manifest_path(settings, task_id).read_text(encoding="utf-8"))
                self.assertTrue(db.get(Task, task_id).has_gt)
                self.assertEqual(manifest["samples"][0]["mask_uri"], sample.mask_uri)
                from app.services.storage import resolve_uri, sha256_file
                self.assertEqual(manifest["samples"][0]["mask_sha256"], sha256_file(resolve_uri(sample.mask_uri, settings)))

        def test_task_first_mask_sees_reference(self):
            def update(db):
                with self.assertRaises(AppError) as caught: self.upload_mask(db)
                self.assertEqual((caught.exception.code, caught.exception.status_code), ("DATASET_FROZEN", 409))
                return "frozen"
            _, result = self.race(DatasetVersion, self.batch_id, self.submit, update,
                prime=lambda db: db.query(Task).all())
            self.assertEqual(result, "frozen")
            with factory() as db: self.assertIsNone(db.get(Sample, self.sample_id).mask_uri)

        def measure(self, db, key):
            version = db.get(ModelVersion, self.model_id)
            profile = perf.request_measure(db, version, db.get(Model, version.model_id), idempotency_key=key)
            return profile.job_id, profile.status

        def test_perf_current_generation(self):
            with factory() as db:
                perf.get_or_create_profile(db, db.get(ModelVersion, self.model_id))
                db.commit()
            first, second = self.race(ModelVersion, self.model_id, lambda db: self.measure(db, "first"),
                lambda db: self.measure(db, "different"),
                prime=lambda db: db.query(ModelPerfProfile).filter_by(version_id=self.model_id).one())
            self.assertEqual(first, second)
            self.assertEqual(first[1], "queued")
            self.assertEqual(self.queue.call_count, 1)

        def test_task_failure_rolls_back_relations(self):
            failure = OperationalError("synthetic lock conflict after insert", {}, RuntimeError("test"))
            with factory() as db, patch.object(tasks, "freeze_inputs", side_effect=failure):
                with self.assertRaises(OperationalError): self.submit(db)
                db.commit()  # Emulates an outer assistant committing its diagnostic turn.
            with factory() as db:
                task_id = submission.request_id("compare", self.user_id, "same")
                for table in (TaskModel, TaskSample):
                    self.assertEqual(db.query(table).filter_by(task_id=task_id).count(), 0)
                self.assertIsNone(db.get(Task, task_id))
            self.queue.assert_not_called()

        def test_real_parent_lock_timeout_leaves_no_task(self):
            failures = []
            with factory() as first:
                first.query(User).filter_by(id=self.user_id).with_for_update().one()
                def contender():
                    try:
                        with factory() as second:
                            second.connection().exec_driver_sql("SET SESSION innodb_lock_wait_timeout = 1")
                            with self.assertRaises(OperationalError) as caught:
                                self.submit(second)
                            self.assertEqual(caught.exception.orig.args[0], 1205)
                            second.rollback()
                            second.commit()
                    except BaseException as exc:
                        failures.append(exc)
                worker = threading.Thread(target=contender, daemon=True)
                worker.start()
                worker.join(10)
                first.rollback()
                worker.join(20)
                self.assertFalse(worker.is_alive())
                if failures: raise failures[0]
            with factory() as db:
                task_id = submission.request_id("compare", self.user_id, "same")
                self.assertIsNone(db.get(Task, task_id))
                for table in (TaskModel, TaskSample):
                    self.assertEqual(db.query(table).filter_by(task_id=task_id).count(), 0)
            self.queue.assert_not_called()

    return unittest.defaultTestLoader.loadTestsFromTestCase(Cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=13306)
    parser.add_argument("--confirm-isolated-test-db", action="store_true")
    args = parser.parse_args()
    if not args.confirm_isolated_test_db or not args.database.startswith("steel_lab_test_"):
        parser.error("explicit isolated-test confirmation and steel_lab_test_* database required; no connection made")
    if not all(c.isascii() and (c.isalnum() or c == "_") for c in args.database):
        parser.error("invalid test database name")
    password = getpass.getpass("Password for the isolated test DB (not stored): ")
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / "apps/api"), str(root / "packages"), str(root / "third_party")]
    sys.dont_write_bytecode = True
    # Only this explicit loopback MySQL port is permitted. asyncio needs its own
    # local socketpair for async upload services; it cannot reach any server.
    local, original_pair = threading.local(), socket.socketpair
    def pair(*a, **kw):
        local.pair = True
        try: return original_pair(*a, **kw)
        finally: local.pair = False
    socket.socketpair = pair
    def audit(name, values):
        if name == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            file = Path(os.fsdecode(values[0])).name.lower()
            if file == ".env" or file.startswith(".env."): raise AssertionError(".env access forbidden")
        if name.startswith("socket.") and not getattr(local, "pair", False):
            if name == "socket.connect" and values[1] != ("127.0.0.1", args.port):
                raise AssertionError("non-test connection forbidden")
            if name == "socket.getaddrinfo" and values[:2] != ("127.0.0.1", args.port):
                raise AssertionError("non-test DNS forbidden")
            if name in {"socket.bind", "socket.sendto"}: raise AssertionError("network forbidden")
        if name in {"subprocess.Popen", "os.system", "os.posix_spawn"}: raise AssertionError("subprocess forbidden")
    sys.addaudithook(audit)
    with tempfile.TemporaryDirectory(prefix="steel-c-mysql-") as work:
        os.environ["MPLCONFIGDIR"] = str(Path(work) / "matplotlib")
        from app import config
        class OfflineSettings(config.Settings):
            model_config = {**config.Settings.model_config, "env_file": None}
            mysql_dsn: str = "sqlite://"  # Never redirect global application engine to MySQL.
            seed_on_start: bool = False
            storage_root: str = str(Path(work) / "storage")
            @classmethod
            def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
                return (init_settings,)
        config.Settings = OfflineSettings
        config.get_settings.cache_clear()
        from sqlalchemy import create_engine, inspect, select, func
        from sqlalchemy.engine import URL
        from app.db.session import Base
        from app.db import models  # register metadata only
        from app import cache
        from admit import dockerutil
        def blocked(*a, **kw): raise AssertionError("external service/executor forbidden")
        cache.rq_connection = cache.cache_redis = blocked
        dockerutil.docker_available = dockerutil.image_present = blocked
        engine = create_engine(URL.create("mysql+pymysql", username=args.user, password=password,
            host="127.0.0.1", port=args.port, database=args.database), isolation_level="REPEATABLE READ",
            connect_args={"connect_timeout": 5, "read_timeout": 20, "write_timeout": 20})
        try:
            # No DDL or cleanup: require an owner-prepared empty schema, otherwise abort.
            with engine.connect() as connection:
                names = set(inspect(connection).get_table_names())
                if names != set(Base.metadata.tables):
                    raise RuntimeError("test schema must contain exactly the pre-provisioned application tables")
                for table in Base.metadata.sorted_tables:
                    if connection.scalar(select(func.count()).select_from(table)):
                        raise RuntimeError("test schema is not empty; refusing to modify existing data")
                engines = connection.exec_driver_sql(
                    "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()").scalars().all()
                if not engines or any(value != "InnoDB" for value in engines):
                    raise RuntimeError("all test tables must use InnoDB")
            result = unittest.TextTestRunner(verbosity=2).run(build_suite(engine, config.get_settings()))
            print("Synthetic database rows retained; temporary filesystem removed. No real queue/Docker/inference.")
            return 0 if result.wasSuccessful() else 1
        finally:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
