from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"


def test_demo_routes_are_public_and_sidebar_lists_demo() -> None:
    router = (WEB / "router" / "index.ts").read_text(encoding="utf-8")
    layout = (WEB / "layouts" / "AppLayout.vue").read_text(encoding="utf-8")
    assert 'path: "demo"' in router
    assert 'path: "demo/:taskId"' in router
    assert "DemoNewView.vue" in router
    assert "DemoTaskView.vue" in router
    assert "meta: { public: true }" in router
    assert "safeAppRedirect" in router
    assert "公开演示" in layout
    assert 'index="/demo"' in layout


def test_demo_views_never_request_metrics_or_upload() -> None:
    new_page = (WEB / "views" / "demo" / "DemoNewView.vue").read_text(encoding="utf-8")
    result = (WEB / "views" / "demo" / "DemoTaskView.vue").read_text(encoding="utf-8")
    login = (WEB / "views" / "LoginView.vue").read_text(encoding="utf-8")
    for token in ("/metrics", "mIoU", "mDice", "el-upload", "/tasks/compare"):
        assert token not in new_page
        assert token not in result
    assert "DEMO_QUOTA" in new_page
    assert "goLogin" in new_page
    assert "redirect:" in new_page and "/demo" in new_page
    assert "safeAppRedirect" in login
    redirect = (WEB / "api" / "redirect.ts").read_text(encoding="utf-8")
    assert "startsWith(\"/\")" in redirect
    assert "://" in redirect
    assert "/demo/tasks" in new_page
    assert "/demo/tasks/" in result
    assert "不展示精度" in new_page
    assert "不计算精度" in result
