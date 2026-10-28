"""Explicit offline admin installer/CPU verification, never invoked by API startup.

python scripts/install_classification_assets.py --source <export.zip> --validate
Existing deployment directories are never overwritten. For a runtime upgrade:
python scripts/install_classification_assets.py --validate-only
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import stat
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
from infer.classification import (  # noqa: E402
    DEFAULT_ROOT, MODEL_SLUGS, THREADS, build_preprocess, inspect_asset,
    load_model, runtime_versions, validate_logits,
)


def install(source: Path, destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Target already exists; no asset files were overwritten. Use --validate-only.")
    allowed = {"weights.pth", "classes.json", "preprocess.json", "model_spec.json", "metadata.json",
               "cpu_validation.json", "evaluation.json", "predictions.csv"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="classification-install-", dir=destination.parent) as scratch:
        staging = Path(scratch) / "payload"
        staging.mkdir()
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > 100 or sum(x.file_size for x in infos) > 700 * 1024 * 1024:
                raise ValueError("Unexpected archive size")
            seen = set()
            for info in infos:
                parts = PurePosixPath(info.filename).parts
                if ("\\" in info.filename or ".." in parts or PurePosixPath(info.filename).is_absolute()
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError("Unsafe archive entry")
                if info.is_dir():
                    continue
                if parts == ("neu_cls_v1_formal_exports", "README.txt"):
                    continue
                if (len(parts) != 3 or parts[0] != "neu_cls_v1_formal_exports"
                        or parts[1] not in MODEL_SLUGS or parts[2] not in allowed):
                    raise ValueError("Unexpected archive member")
                relative = Path(parts[1]) / parts[2]
                if relative in seen:
                    raise ValueError("Duplicate archive member")
                seen.add(relative)
                limit = 150 * 1024 * 1024 if parts[2] == "weights.pth" else 1024 * 1024
                if info.file_size > limit:
                    raise ValueError("Archive member too large")
                target = staging / relative
                target.parent.mkdir(exist_ok=True)
                with archive.open(info) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        # Validate all six byte hashes/protocols before making the deployment visible.
        for slug in MODEL_SLUGS:
            inspect_asset(slug, staging, require_validated=False)
        staging.rename(destination)


def peak_rss_bytes() -> int | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                          "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                          "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = wintypes.HANDLE
        measure = ctypes.windll.psapi.GetProcessMemoryInfo
        measure.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        measure.restype = wintypes.BOOL
        if measure(process(), ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024))


def validate(root: Path, report_dir: Path) -> bool:
    import numpy as np
    import torch
    from PIL import Image
    torch.set_num_threads(THREADS)
    versions = runtime_versions()
    rows = []
    # Deterministic synthetic pixels: no test set, labels, accuracy or GT access.
    pixels = np.arange(200 * 200 * 3, dtype=np.uint8).reshape(200, 200, 3)
    square = Image.fromarray(pixels)
    rectangle = Image.fromarray(np.tile(pixels, (1, 2, 1)))
    for slug in MODEL_SLUGS:
        row = {"slug": slug, "ok": False, "runtime": versions, "threads": THREADS,
               "validation_source": "deterministic synthetic RGB images; no ground truth",
               "device": "cpu", "strict": True, "weights_only": True, "weights": None}
        try:
            begin = time.perf_counter()
            asset = inspect_asset(slug, root, require_validated=False)
            row["asset_check_ms"] = (time.perf_counter() - begin) * 1000
            row.update(asset_hash=asset.asset_hash, weight_sha256=asset.weight_sha256,
                       classes_hash=asset.classes_hash, preprocess_hash=asset.preprocess_hash,
                       protocol_hash=asset.protocol_hash, param_count=asset.param_count)
            begin = time.perf_counter()
            module = load_model(asset)
            row["load_ms"] = (time.perf_counter() - begin) * 1000
            transform = build_preprocess(asset)
            begin = time.perf_counter()
            tensor = transform(square).unsqueeze(0)
            rect = transform(rectangle).unsqueeze(0)
            row["preprocess_two_images_ms"] = (time.perf_counter() - begin) * 1000
            row["input_b1"] = list(tensor.shape)
            row["input_rectangle"] = list(rect.shape)
            assert list(rect.shape) == [1, 3, 224, 448]
            with torch.inference_mode():
                one = module(tensor)
                two = module(tensor.repeat(2, 1, 1, 1))
                rectangular = module(rect)
                validate_logits(one, 1)
                validate_logits(two, 2)
                validate_logits(rectangular, 1)
                row.update(shape_b1=list(one.shape), shape_b2=list(two.shape),
                           shape_rectangle=list(rectangular.shape), finite=True)
                for _ in range(3):
                    module(tensor)
                durations = []
                for _ in range(10):
                    begin = time.perf_counter()
                    output = module(tensor)
                    durations.append((time.perf_counter() - begin) * 1000)
                    validate_logits(output, 1)
            row.update(ok=True, warmup_runs=3, timed_runs=10,
                       forward_ms_p50=float(np.percentile(durations, 50)),
                       forward_ms_p95=float(np.percentile(durations, 95)),
                       forward_ms_samples=durations, peak_process_rss_bytes=peak_rss_bytes(),
                       measured_at=datetime.now(timezone.utc).isoformat())
            del module, tensor, rect, one, two, rectangular, output
            gc.collect()
        except Exception as exc:
            # Only safe typed/public errors are serialized; no local path or traceback.
            row["reason"] = f"CPU validation failed ({type(exc).__name__})"
        rows.append(row)
        folder = root / slug
        if folder.is_dir():
            temp = folder / "validated.json.tmp"
            temp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(folder / "validated.json")
        print(f"{slug}: {'PASS' if row['ok'] else 'FAIL'}", flush=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {"runtime": versions, "threads": THREADS,
               "latency_scope": "CPU model forward only; B=1, 3x224x224; preprocessing/loading separately timed",
               "rss_scope": "Process lifetime peak working set, sequential models; includes Python/runtime/allocator; not per-model incremental memory",
               "rows": rows}
    (report_dir / "asset-validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return all(row["ok"] for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "docs/report/classification-2026-10-28")
    args = parser.parse_args()
    # Explicit offline barrier, installed before importing the inference runtime.
    def audit(event, values):
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(values[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise RuntimeError("Environment files are forbidden during asset validation")
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("Network is forbidden during asset validation")
    sys.addaudithook(audit)
    if not args.validate_only:
        if args.source is None:
            parser.error("--source is required unless --validate-only")
        install(args.source, args.root)
    if args.validate or args.validate_only:
        return 0 if validate(args.root, args.report_dir) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
