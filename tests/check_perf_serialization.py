"""Offline regression for CPU performance publication; no live service or inference.

Run: .venv/Scripts/python.exe -B tests/check_perf_serialization.py
The shared bootstrap forbids .env, network and subprocess access before app import.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from check_demo_model_specs import load_offline_application


class PerformancePublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, _ = load_offline_application()
        from admit.perf import fps_from_latency_ms
        from app.services import perf
        from starlette.responses import JSONResponse

        cls.fps = staticmethod(fps_from_latency_ms)
        cls.perf = perf
        cls.response = JSONResponse

    def fixture(self, **changes):
        model = self.models.Model(id="model", source="builtin", name="fixture")
        version = self.models.ModelVersion(
            id="version", model_id=model.id, status="runnable", requires_cuda=False,
            slug="unet", input_h=200, input_w=200, num_classes=4, in_channels=3,
            preprocess_id="preprocess", visibility="public",
        )
        profile = self.models.ModelPerfProfile(
            id="profile", version_id=version.id, status="success", param_count=100,
            latency_ms_per_image=250.0, batch=1, input_h=200, input_w=200,
            device="cpu", input_kind="dummy", warmup_runs=3, timed_runs=10,
        )
        for key, value in changes.items():
            setattr(profile, key, value)
        query = Mock()
        query.filter.return_value = query
        query.one_or_none.return_value = profile
        db = Mock()
        db.query.return_value = query
        return model, version, profile, db

    def serialize(self, **changes):
        model, version, _, db = self.fixture(**changes)
        return self.perf.serialize_perf(db, version, model, settings=SimpleNamespace())

    def test_valid_speed_keeps_units_and_rounding(self):
        self.assertEqual(self.fps(250.0), 4.0)
        self.assertEqual(self.fps(12.5), 80.0)

    def test_nonfinite_and_nonpositive_latency_never_becomes_speed(self):
        for latency in [None, 0, -1, math.nan, math.inf, -math.inf]:
            with self.subTest(latency=latency):
                self.assertIsNone(self.fps(latency))

    def test_overflowed_derived_speed_is_unknown(self):
        self.assertIsNone(self.fps(5e-324))

    def test_invalid_profile_is_json_serializable_without_speed(self):
        for latency in [None, 0, -1, math.nan, math.inf, -math.inf, 5e-324]:
            with self.subTest(latency=latency):
                row = self.serialize(latency_ms_per_image=latency)
                self.assertIsNone(row["latency_ms_per_image"])
                self.assertIsNone(row["fps_per_image"])
                self.assertEqual(self.response(row).status_code, 200)

    def test_pending_or_failed_remeasure_does_not_publish_old_speed(self):
        for state in ["queued", "measuring", "failed", "unmeasured"]:
            with self.subTest(state=state):
                row = self.serialize(status=state)
                self.assertEqual(row["status"], state)
                self.assertIsNone(row["latency_ms_per_image"])
                self.assertIsNone(row["fps_per_image"])

    def test_mismatched_protocol_is_not_cpu_current_input_speed(self):
        for change in [{"device": "cuda"}, {"batch": 2}, {"input_kind": "dataset"},
                       {"input_h": 512}, {"input_w": None}]:
            with self.subTest(change=change):
                row = self.serialize(**change)
                self.assertIsNone(row["latency_ms_per_image"])
                self.assertIsNone(row["fps_per_image"])

    def test_valid_completed_profile_is_preserved(self):
        row = self.serialize()
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["param_count"], 100)
        self.assertEqual(row["latency_ms_per_image"], 250.0)
        self.assertEqual(row["fps_per_image"], 4.0)
        self.assertEqual(self.response(row).status_code, 200)

    def test_invalid_result_is_rejected_before_database_access(self):
        for latency in [None, 0, -1, math.nan, math.inf, -math.inf, 5e-324, "invalid"]:
            with self.subTest(latency=latency):
                model, version, _, _ = self.fixture()
                db = Mock()
                db.query.side_effect = AssertionError("invalid result touched database")
                with self.assertRaisesRegex(ValueError, "latency"):
                    self.perf.apply_measure_result(
                        db, version, model, {"latency_ms_per_image": latency},
                        settings=SimpleNamespace(),
                    )
                db.query.assert_not_called()

    def test_valid_result_persists_and_serializes(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.db.session import Base

        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                model, version, profile, _ = self.fixture(status="measuring")
                db.add_all([model, version, profile])
                db.commit()
                self.perf.apply_measure_result(
                    db, version, model,
                    {"latency_ms_per_image": 12.5, "param_count": 120, "weight_bytes": 128},
                    settings=SimpleNamespace(),
                )
                db.commit()
                row = self.perf.serialize_perf(db, version, model, settings=SimpleNamespace())
                self.assertEqual(row["status"], "success")
                self.assertEqual(row["latency_ms_per_image"], 12.5)
                self.assertEqual(row["fps_per_image"], 80.0)
                self.assertEqual(row["param_count"], 120)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
