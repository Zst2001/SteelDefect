from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

from app.services.demo import payload_has_no_metric_fields


def test_readme_describes_dual_surface_and_demo_smoke() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "公开演示" in readme
    assert "/demo" in readme
    assert "scripts/smoke_h.py" in readme
    assert "smoke_ac01.py" in readme
    assert "smoke_f.py" in readme
    assert "HomeView" in readme or "首页综述" in readme
    assert "不做训练" in readme


def test_smoke_h_covers_ac10_to_ac13() -> None:
    smoke = (ROOT / "scripts" / "smoke_h.py").read_text(encoding="utf-8")
    for token in ("AC-10", "AC-11", "AC-12", "AC-13", "DEMO_QUOTA", "DEMO_NO_METRICS", "REGISTER_DISABLED"):
        assert token in smoke
    assert "明日再试或登录" in smoke
    assert "/uploads/images" in smoke
    assert "metrics.json" in smoke
    assert "lab:demo:" in smoke
    ac01 = (ROOT / "scripts" / "smoke_ac01.py").read_text(encoding="utf-8")
    assert "trust_env=False" in ac01
    assert "trust_env=False" in (ROOT / "scripts" / "smoke_c.py").read_text(encoding="utf-8")
    assert "trust_env=False" in (ROOT / "scripts" / "smoke_d.py").read_text(encoding="utf-8")


def test_quota_and_no_metrics_unit_tests_still_present() -> None:
    h3 = (ROOT / "tests" / "test_slice_h3.py").read_text(encoding="utf-8")
    h4 = (ROOT / "tests" / "test_slice_h4.py").read_text(encoding="utf-8")
    jobs = (ROOT / "apps" / "worker" / "jobs.py").read_text(encoding="utf-8")
    demo = (WEB / "views" / "demo" / "DemoTaskView.vue").read_text(encoding="utf-8")
    login = (WEB / "views" / "LoginView.vue").read_text(encoding="utf-8")
    assert "DEMO_NO_METRICS" in h3
    assert "payload_has_no_metric_fields" in h3
    assert "DEMO_QUOTA" in h4
    assert "明日再试或登录" in h4
    assert "logged_in_demo_skips_guest_quota" in h4
    assert "and not demo_mode" in jobs
    assert "run_demo" in jobs
    assert "mIoU" not in demo and "mDice" not in demo and "/metrics" not in demo
    assert "自助注册" in login
    assert "导师开通" in login
    assert 'to="/register"' not in login
    assert "submitRegister" not in login
    assert "el-upload" not in (WEB / "views" / "demo" / "DemoNewView.vue").read_text(encoding="utf-8")


def test_metric_leak_detector_ignores_uuid_and_success_status() -> None:
    clean = {
        "id": "accaccac-acc0-4cc0-acc0-accaccaccacc",
        "status": "success",
        "disclaimer": "公开演示 / 预备样例 / 不代表测试集性能",
        "models": [{"name": "UNet", "status": "success"}],
    }
    assert payload_has_no_metric_fields(clean)
    assert not payload_has_no_metric_fields({"id": "x", "miou": 0.12})
    assert not payload_has_no_metric_fields({"metrics": {"available": False}})
