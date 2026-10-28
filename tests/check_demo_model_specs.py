"""Offline public-model catalog checks; run with Python -B, no .env or services.

Loads the production serializer with init-only settings. Uses transient ORM
objects and a private in-memory SQLite DB for the list/eager-loading check.
Does not open weight files, measure models, run inference or call the live API.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_offline_application():
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT), str(ROOT / "apps/api"), str(ROOT / "packages")]

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise AssertionError("Catalog checks forbid .env access")
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo",
                     "subprocess.Popen", "os.system", "os.posix_spawn"}:
            raise AssertionError("Catalog checks forbid network and process execution")

    sys.addaudithook(audit)
    from app import config

    class OfflineSettings(config.Settings):
        model_config = {**config.Settings.model_config, "env_file": None}
        mysql_dsn: str = "sqlite://"
        seed_on_start: bool = False

        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                       dotenv_settings, file_secret_settings):
            return (init_settings,)

    config.Settings = OfflineSettings
    config.get_settings.cache_clear()
    from app.db import models
    from app.services import demo
    return models, demo


class PublicModelSpecs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, cls.demo = load_offline_application()

    def fixture(self, **profile_changes):
        model = self.models.Model(id="model", name="UNet", source="builtin")
        version = self.models.ModelVersion(
            id="version", model_id=model.id, slug="unet", num_classes=4,
            in_channels=3, input_h=200, input_w=200, requires_cuda=False,
            status="runnable", preprocess_id="preprocess", visibility="public",
        )
        profile = self.models.ModelPerfProfile(
            id="profile", version_id=version.id, status="success", device="cpu",
            batch=1, input_kind="dummy", input_h=200, input_w=200,
            latency_ms_per_image=500.0, param_count=2_000_000,
            env_json={"private": "must not be serialized"},
            fail_message="private diagnostic", job_id="private-job",
        )
        for key, value in profile_changes.items():
            setattr(profile, key, value)
        return model, version, profile

    def test_successful_persisted_specs(self):
        model, version, profile = self.fixture()
        row = self.demo.serialize_demo_model(model, version, profile=profile)
        self.assertEqual(row["param_count"], 2_000_000)
        self.assertEqual(row["fps_per_image"], 2.0)

    def test_missing_specs_are_null(self):
        model, version, _ = self.fixture()
        row = self.demo.serialize_demo_model(model, version)
        self.assertIsNone(row["param_count"])
        self.assertIsNone(row["fps_per_image"])

    def test_parameter_fallback_reads_metadata_without_weight_file(self):
        model, version, profile = self.fixture(status="failed")
        version.weights = [self.models.Weight(id="weight", version_id=version.id,
                            file_uri="not-a-file", sha256="unused", param_count=1_000_000)]
        row = self.demo.serialize_demo_model(model, version, profile=profile)
        self.assertEqual(row["param_count"], 1_000_000)
        self.assertIsNone(row["fps_per_image"])

    def test_only_matching_completed_cpu_protocol_exposes_speed(self):
        for changes in [{"status": "failed"}, {"status": "queued"},
                        {"status": "measuring"}, {"device": "cuda"},
                        {"batch": 2}, {"input_kind": "dataset"},
                        {"input_h": 512}, {"input_w": None}]:
            with self.subTest(changes=changes):
                model, version, profile = self.fixture(**changes)
                row = self.demo.serialize_demo_model(model, version, profile=profile)
                self.assertIsNone(row["fps_per_image"])

    def test_invalid_latency_is_not_shown_as_speed(self):
        for latency in [None, 0, -1, math.inf, -math.inf, math.nan]:
            with self.subTest(latency=latency):
                model, version, profile = self.fixture(latency_ms_per_image=latency)
                row = self.demo.serialize_demo_model(model, version, profile=profile)
                self.assertIsNone(row["fps_per_image"])

    def test_zero_parameters_is_real_and_negative_is_unknown(self):
        for params, expected in [(0, 0), (-1, None)]:
            with self.subTest(params=params):
                model, version, profile = self.fixture(param_count=params)
                row = self.demo.serialize_demo_model(model, version, profile=profile)
                self.assertEqual(row["param_count"], expected)

    def test_public_field_allowlist_omits_private_and_accuracy_data(self):
        model, version, profile = self.fixture()
        row = self.demo.serialize_demo_model(model, version, profile=profile)
        self.assertEqual(set(row), {"id", "name", "slug", "source", "num_classes",
                                  "input_size", "requires_cuda", "runnable_here",
                                  "param_count", "fps_per_image"})
        self.assertTrue(self.demo.catalog_has_no_gt_fields(row))
        self.assertTrue(self.demo.payload_has_no_metric_fields(row))

    def test_list_uses_persisted_relationships_and_preserves_eligibility(self):
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import Session
        from app.db.session import Base

        engine = create_engine("sqlite://")
        statements = []
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                for i, (slug, source, status, cuda) in enumerate([
                    ("unet", "builtin", "runnable", False),
                    ("bisenet", "builtin", "runnable", False),
                    ("danet", "student", "runnable", False),
                    ("pspnet", "builtin", "failed", False),
                    ("segformer", "builtin", "runnable", True),
                ]):
                    model, version, profile = self.fixture()
                    model.id, model.source = f"model-{i}", source
                    version.id, version.model_id = f"version-{i}", model.id
                    version.slug, version.status, version.requires_cuda = slug, status, cuda
                    profile.id, profile.version_id = f"profile-{i}", version.id
                    db.add_all([model, version, profile])
                db.commit()
                db.expire_all()
                event.listen(engine, "before_cursor_execute",
                             lambda conn, cursor, statement, *rest: statements.append(statement))
                result = self.demo.list_demo_models(db)
                self.assertEqual([row["slug"] for row in result["items"]], ["unet", "bisenet"])
                self.assertTrue(all(row["fps_per_image"] == 2.0 for row in result["items"]))
                self.assertEqual(len(statements), 4)
                self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in statements))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
