"""Run the reviewed phase-A tests offline, BEFORE importing application modules.

Usage: .venv/Scripts/python.exe -B tests/run_phase_a_tests.py
Optional pytest node IDs must belong to DEFAULT_TARGETS' reviewed files.
No production lifespan, .env, network clients, subprocesses or real inference.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/api"), str(ROOT / "packages"), str(ROOT / "third_party")]
sys.dont_write_bytecode = True

DEFAULT_TARGETS = [
    "tests/test_phase_a_authorization.py",
    "tests/test_task_artifact_access.py",
    "tests/test_phase_c_reliability.py",
    "tests/test_phase_c_repairs.py",
    "tests/test_phase_c_acceptance.py",
    "tests/test_classification_backend.py",
    "tests/test_classification_infer.py",
    "tests/test_classification_boundaries.py",
    "tests/test_pcb_backend.py",
    "tests/test_pcb_batch.py",
    "tests/test_pcb_tiling.py",
    "tests/test_pcb_classification.py",
    "tests/test_slice_g.py", "tests/test_slice_c.py", "tests/test_slice_e.py",
    "tests/test_slice_f.py", "tests/test_slice_h3.py", "tests/test_slice_d.py",
    "tests/test_scenes_empty.py", "tests/test_metrics_policy.py",
    *[f"tests/test_slice_assistant.py::{name}" for name in (
        "test_ai01_no_key_returns_pack_without_writing", "test_ai02_demo_rejected_without_metrics",
        "test_ai03_no_gt_pack_omits_accuracy_numbers", "test_ai08_cannot_analyze_unsubmitted_peer",
        "test_ai09_advisor_can_analyze_submitted", "test_ai12_session_turn_and_audit_persist",
        "test_running_task_not_ready", "test_closed_specialty_rejected",
        "test_ai04_infer_rejects_demo_and_eval_batches", "test_ai05_catalog_not_runnable",
        "test_ai04_infer_confirm_then_compare", "test_academic_cannot_run_infer",
        "test_ai06_detect_unavailable", "test_m01_code_advise_does_not_write",
    )],
    *[f"tests/test_slice_adapt.py::{name}" for name in (
        "test_ad01_apply_appends_and_requeues", "test_ad02_decline_keeps_hash",
        "test_ad04_apply_does_not_mark_runnable", "test_ad05_load_has_no_apply",
        "test_ad06_cannot_adapt_others",
    )],
]


def blocked(*_args, **_kwargs):
    raise AssertionError("Phase A isolation blocked an external service or execution")


def main() -> int:
    # Only asyncio's own socketpair may open sockets. All service/network I/O is denied.
    local = threading.local()
    original_pair = socket.socketpair

    def local_pair(*args, **kwargs):
        local.socketpair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            local.socketpair = False

    socket.socketpair = local_pair

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise AssertionError("Phase A isolation forbids reading .env files")
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo"}:
            if not getattr(local, "socketpair", False):
                blocked()
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn"}:
            blocked()

    sys.addaudithook(audit)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    with tempfile.TemporaryDirectory(prefix="steel-phase-a-") as work:
        os.environ["MPLCONFIGDIR"] = str(Path(work) / "matplotlib")
        from app import config

        class OfflineSettings(config.Settings):
            model_config = {**config.Settings.model_config, "env_file": None}
            storage_root: str = str(Path(work) / "storage")
            seed_on_start: bool = False
            mysql_dsn: str = "sqlite://"

            @classmethod
            def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                           dotenv_settings, file_secret_settings):
                return (init_settings,)

        config.Settings = OfflineSettings
        config.get_settings.cache_clear()
        assert config.get_settings().mysql_dsn == "sqlite://"

        # Native clients (e.g. grpc) need a Python-level barrier in addition to socket audit.
        import pymysql
        import redis
        import rq
        import httpx
        import dotenv

        # pymilvus.settings calls load_dotenv during import, independently of Settings.
        dotenv.load_dotenv = lambda *a, **k: False
        dotenv.main.load_dotenv = dotenv.load_dotenv
        import pymilvus
        import grpc

        pymysql.connect = blocked
        pymysql.connections.Connection.connect = blocked
        redis.Redis.execute_command = blocked
        rq.Queue.enqueue = blocked
        httpx.HTTPTransport.handle_request = blocked
        httpx.AsyncHTTPTransport.handle_async_request = blocked
        pymilvus.MilvusClient = blocked
        grpc.insecure_channel = blocked
        grpc.secure_channel = blocked

        from app.services import assistant, assistant_kb, kb_embed, llm_client
        from admit import dockerutil
        from infer import engine
        import torch

        for module, names in (
            (assistant, ("retrieve_kb", "draft_analyze_copy", "draft_code_advice", "draft_kb_copy", "iter_chat_completion")),
            (assistant_kb, ("retrieve_kb",)),
            (kb_embed, ("embed_text",)),
            (llm_client, ("chat_completion", "iter_chat_completion")),
            (dockerutil, ("docker_available", "image_present")),
            (engine, ("get_builtin_module", "predict_mask")),
            # Keep classification argument/loader contracts testable. Tests may
            # mock torch.load, but the default runner cannot read real weights.
            (torch, ("load",)),
        ):
            for name in names:
                setattr(module, name, blocked)

        import pytest

        targets = sys.argv[1:] or DEFAULT_TARGETS
        # Prevent accidentally using this curated runner for unreviewed inference/smoke tests.
        whole_files = {node for node in DEFAULT_TARGETS if "::" not in node}
        if any(node not in DEFAULT_TARGETS and node.split("::")[0] not in whole_files for node in targets):
            raise SystemExit("Only reviewed phase-A test targets are allowed")
        print("Isolation: init-only settings, SQLite, temporary storage, no .env/network/subprocess/real executors")
        return pytest.main(["-q", "-rs", "-p", "no:cacheprovider", "--basetemp", str(Path(work) / "pytest"), *targets])


if __name__ == "__main__":
    raise SystemExit(main())
