"""Explicit offline Windows CPU admission and benchmark; never train or enable API.

Predetermined cross-version FP32 tolerance: abs(error) <= .001 + .0001*abs(ref).
Creates a private receipt only after both models pass. Original smoke remains
independent evidence; its stricter threshold is never modified by this script.
"""
import argparse
import ctypes
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
platform.uname()


def offline(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("Offline admission forbids network access")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)) and Path(os.fsdecode(args[0])).name.lower().startswith(".env"):
        raise RuntimeError("Admission never reads environment files")


sys.addaudithook(offline)


def memory():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    row = Counters()
    row.cb = ctypes.sizeof(row)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(row), row.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return {"rss_bytes": row.WorkingSetSize, "peak_rss_bytes": row.PeakWorkingSetSize}


def main():
    if sys.flags.optimize:
        raise RuntimeError("Admission requires assertions enabled; do not use -O or PYTHONOPTIMIZE")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise RuntimeError("Choose a fresh evidence report")
    import numpy as np
    import torch
    from PIL import Image
    from infer.pcb_classification import catalog as identity
    from infer.pcb_classification import runtime
    root = ROOT / "assets/pcb_classification/deeppcb_roi_v0_formal_v1"
    torch.set_num_threads(identity.THREADS)
    torch.set_num_interop_threads(identity.INTEROP)
    assert platform.system() == "Windows" and torch.backends.mkldnn.enabled
    verify_started = time.perf_counter()
    configs = identity.verify_release(root)["configs"]
    release_verification_ms = (time.perf_counter() - verify_started) * 1000
    reference = json.loads((root / "validation/cpu_smoke_results.json").read_text(encoding="utf-8"))["models"]
    yy, xx = np.indices((224, 224))
    gray = Image.fromarray(((xx * 3 + yy * 5 + 17) % 256).astype(np.uint8))
    png = io.BytesIO()
    gray.save(png, format="PNG")
    content = png.getvalue()
    x = runtime.tensor_from_gray(gray, configs["preprocess"])
    assert x.shape == (1, 3, 224, 224) and x.dtype == torch.float32 and torch.equal(x[:, 0], x[:, 2])
    from infer.pcb_classification.images import decode
    assert np.array_equal(np.asarray(decode(content, "roi.png", "image/png")[0]), np.asarray(gray))
    report = {"status": "RUNNING", "protocol_id": identity.PROTOCOL, "zip_sha256": identity.ZIP_SHA,
              "manifest_sha256": identity.MANIFEST_SHA, "source_hash": identity.source_hash(),
              "runtime": identity.runtime_identity(), "tolerance": {"atol": .001, "rtol": .0001},
              "release_verification_ms": release_verification_ms,
              "warmup": 3, "samples": 20, "models": {}, "scope": "synthetic CPU correctness/performance, not accuracy"}
    for key, spec in identity.MODELS.items():
        before = memory()
        started = time.perf_counter()
        model = runtime.strict_load(key, root)
        load_ms = (time.perf_counter() - started) * 1000
        after_load = memory()
        with torch.inference_mode():
            actual = model(x).numpy()[0]
            expected = np.asarray(reference[key]["logits"])
            error = np.abs(actual - expected)
            violations = np.flatnonzero(error > .001 + .0001 * np.abs(expected)).tolist()
            assert not violations and np.isfinite(actual).all() and int(actual.argmax()) == reference[key]["class_id"]
            synthetic = []
            for pixels in (np.full((224, 224), 127, dtype=np.uint8), ((xx // 8 + yy // 8) % 2 * 255).astype(np.uint8)):
                tx = runtime.tensor_from_gray(Image.fromarray(pixels), configs["preprocess"])
                a, b = model(tx), model(tx)
                assert torch.equal(a, b)
                result = runtime.checked_output(a, key, configs["classes"]["classes"], {"input_adapted": False})
                synthetic.append({"finite": True, "stable": True, "class_id": result["class_id"], "sum": sum(result["probabilities"])})
            for _ in range(3):
                model(x)
            forward, full = [], []
            for _ in range(20):
                begin = time.perf_counter()
                model(x)
                forward.append((time.perf_counter() - begin) * 1000)
                begin = time.perf_counter()
                im, meta = decode(content, "roi.png", "image/png")
                output = model(runtime.tensor_from_gray(im, configs["preprocess"]))
                json.dumps(runtime.checked_output(output, key, configs["classes"]["classes"], meta), ensure_ascii=False)
                full.append((time.perf_counter() - begin) * 1000)
        report["models"][key] = {"passed": True, "weight_sha256": spec[0], "strict": True, "weights_only": True,
            "missing_keys": 0, "unexpected_keys": 0, "parameters": sum(p.numel() for p in model.parameters()),
            "load_ms": load_ms, "memory_before": before, "memory_after_load": after_load, "memory_after_inference": memory(),
            "logits": actual.tolist(), "reference": expected.tolist(), "max_abs_error": float(error.max()),
            "max_rel_error": float((error / np.maximum(np.abs(expected), 1e-12)).max()), "violations": violations,
            "class_id": int(actual.argmax()), "synthetic": synthetic,
            "forward_ms": forward, "full_ms": full,
            "forward_p50_ms": float(np.percentile(forward, 50)), "forward_p95_ms": float(np.percentile(forward, 95)),
            "full_p50_ms": float(np.percentile(full, 50)), "full_p95_ms": float(np.percentile(full, 95))}
        print(f"{key}: strict PASS, max_abs={error.max():.8g}; full P50/P95 {np.percentile(full,50):.2f}/{np.percentile(full,95):.2f} ms", flush=True)
        del model
    report["status"] = "PASS"
    receipt = root / identity.RECEIPT
    # Never silently replace a prior receipt; source changes need explicit readmission.
    with receipt.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, allow_nan=False)
    try:
        with patch.object(torch, "load", wraps=torch.load) as loads, patch.object(identity, "digest", wraps=identity.digest) as hashes:
            a, _ = runtime.predict(root, identity.DEFAULT, content, "roi.png")
            load_count, hash_count = loads.call_count, hashes.call_count
            b, _ = runtime.predict(root, identity.DEFAULT, content, "roi.png")
            assert not a["cache_hit"] and b["cache_hit"] and loads.call_count == load_count == 1 and hashes.call_count == hash_count
            assert a["probabilities"] == b["probabilities"]
            report["cache"] = {"first_hit": False, "second_hit": True, "torch_load_calls": loads.call_count,
                               "additional_hash_calls_on_repeat": hashes.call_count - hash_count, "capacity": 1}
    except BaseException:
        receipt.unlink()  # This attempt's newly created receipt only; never leave a false PASS.
        raise
    with args.report.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
