"""Offline stage-4A admission and independent-process CPU measurements.

Run with the project's Worker interpreter. Never imports application settings,
reads .env, calls external services, or changes the verified asset directory.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
from infer.pcb.runtime import MODELS, ROOT as ASSET_ROOT, load_model
from infer.pcb.catalog import (MANIFEST_SHA256, PROTOCOL_HASH, runtime_versions,
                              source_hashes, receipt_path, verify_staging)


def deny_external_io():
    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise RuntimeError("Offline PCB verification forbids .env")
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo",
                     "subprocess.Popen", "os.system", "os.posix_spawn"}:
            raise RuntimeError("Offline PCB verification forbids network/child execution")
    sys.addaudithook(audit)


def memory():
    """Windows current working set and OS process-lifetime peak, in bytes."""
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not get_info(process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"rss_bytes": counters.WorkingSetSize, "lifetime_peak_rss_bytes": counters.PeakWorkingSetSize}


class SampleMemory:
    def __enter__(self):
        self.stop = threading.Event()
        self.peak = memory()["rss_bytes"]
        def sample():
            while not self.stop.wait(0.01):
                self.peak = max(self.peak, memory()["rss_bytes"])
        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.peak = max(self.peak, memory()["rss_bytes"])
        self.stop.set()
        self.thread.join()


def reference_inputs():
    # Exact reviewed tools/reference_input.py generator, no asset code execution.
    import numpy as np
    rng = np.random.RandomState(20261029)
    image = np.zeros((220, 220, 3), dtype=np.uint8)
    image[:] = rng.randint(0, 50, size=(220, 220, 3), dtype=np.uint8)
    image[10:70, 15:90] = rng.randint(80, 180, size=(60, 75, 3), dtype=np.uint8)
    image[120:180, 20:200:5] = np.array([210, 30, 30], dtype=np.uint8)
    image[0, :] = 255
    image[-1, :] = 0
    image[:, 0] = 128
    image[:, -1] = 64
    return {"textured": image, "black": np.zeros_like(image), "gray": np.full_like(image, 128)}


def compare_logits(actual, expected):
    import numpy as np
    assert actual.shape == expected.shape == (1, 2, 256, 256)
    assert np.isfinite(actual).all() and np.isfinite(expected).all()
    diff = np.abs(actual - expected)
    limits = 1e-3 + 1e-4 * np.abs(expected)
    result = {"max_abs": float(diff.max()), "max_rel": float((diff / np.maximum(np.abs(expected), 1e-8)).max()),
              "outside_tolerance": int((diff > limits).sum()), "atol": 1e-3, "rtol": 1e-4}
    for space, slices in (("canvas_256", (slice(None), slice(None))),
                          ("original_220", (slice(18, 238), slice(18, 238)))):
        pred = actual.argmax(1)[0][slices]
        ref = expected.argmax(1)[0][slices]
        different = pred != ref
        intersection = int(((pred == 1) & (ref == 1)).sum())
        union = int(((pred == 1) | (ref == 1)).sum())
        result[space] = {"mask_agreement": float((~different).mean()),
            "reference_foreground": int((ref == 1).sum()), "local_foreground": int((pred == 1).sum()),
            "mismatch_pixels": int(different.sum()), "foreground_intersection": intersection,
            "foreground_union": union, "foreground_iou": intersection / union if union else None,
            "difference_coordinates_yx": np.argwhere(different).tolist()}
    result["passed"] = result["outside_tolerance"] == 0 and result["original_220"]["mask_agreement"] >= .999
    return result


def percentiles(samples):
    import numpy as np
    return {"p50_ms": float(np.percentile(samples, 50)), "p95_ms": float(np.percentile(samples, 95)),
            "samples_ms": samples}


def bench(call, warmup, repeats):
    for _ in range(warmup):
        call()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append((time.perf_counter() - start) * 1000)
    return percentiles(samples)


def child(args):
    # platform collection may internally use a subprocess; collect before guard.
    machine = platform.platform()
    before_import = memory()
    deny_external_io()
    import cv2
    import numpy as np
    import torch
    from infer.pcb.preprocess import prepare_canvas
    from infer.pcb.postprocess import mask_and_probability, to_numpy
    from infer.pcb.visualize import SegmentationGradCAM, predict_layers
    torch.set_num_threads(args.threads)
    if args.interop is not None:
        torch.set_num_interop_threads(args.interop)
    torch.backends.mkldnn.enabled = not args.no_mkldnn
    cv2.setNumThreads(1)
    root = Path(args.assets).resolve()
    # Anchor every reference/source/weight to the independently verified original
    # ZIP, not a potentially modified local manifest or recorded receipt.
    from verify_pcb_assets import verify_release
    from hashlib import sha256
    frozen = verify_release(ROOT / "assets/PCB_segment/pcb_seg_meiwei_v2_formal_v1.zip")
    verify_staging(root)
    for name, identity in frozen["files"].items():
        with (root / name).open("rb") as stream:
            digest = sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != identity["sha256"]:
            raise ValueError("Private staging differs from frozen ZIP")
    result = {"model_id": args.model, "time_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"executable": sys.executable, "python": sys.version, "platform": machine,
                        "cpu": platform.processor(), "torch": torch.__version__,
                        "torchvision": importlib.metadata.version("torchvision"), "numpy": np.__version__,
                        "Pillow": importlib.metadata.version("Pillow"), "cv2": cv2.__version__,
                        "threads": torch.get_num_threads(), "interop": torch.get_num_interop_threads(),
                        "mkldnn": torch.backends.mkldnn.enabled},
        "memory": {"before_torch_import": before_import, "before_load": memory()},
        "deployment": "offline process using configured Windows Worker .venv; no running queue",
        "source_status": "admission_only_not_website_enabled", "failures": []}
    start = time.perf_counter()
    model = load_model(args.model, root, threads=args.threads)
    result["load_ms"] = (time.perf_counter() - start) * 1000
    result["memory"]["after_load"] = memory()
    result["strict_loading"] = {"weights_only": True, "strict": True, "missing_keys": [],
                               "unexpected_keys": [], "params": sum(p.numel() for p in model.parameters()),
                               "cam_layer": model.cam_layer_name, "eval": not model.training}
    inputs = reference_inputs()
    result["preprocess"] = []
    for key, made in inputs.items():
        suffix = "" if key == "textured" else "_" + key
        filename = "input_220_rgb.npy" if key == "textured" else f"input_{key}_220_rgb.npy"
        saved = np.load(root / "reference_vectors" / filename, allow_pickle=False)
        expected = np.load(root / "reference_vectors" / f"expected_preprocessed{suffix}.npy", allow_pickle=False)
        actual = prepare_canvas(saved).numpy()
        row = {"input": key, "input_exact": bool(np.array_equal(made, saved)),
               "preprocess_exact": actual.dtype == expected.dtype == np.float32 and bool(np.array_equal(actual, expected))}
        result["preprocess"].append(row)
        if not row["input_exact"] or not row["preprocess_exact"]:
            result["failures"].append("preprocess:" + key)
    tensor = prepare_canvas(inputs["textured"])
    with torch.no_grad():
        actual = model(tensor).numpy()
    expected = np.load(root / "reference_vectors" / f"{args.model}_logits.npy", allow_pickle=False)
    result["cross"] = compare_logits(actual, expected)
    if not result["cross"]["passed"]:
        result["failures"].append("cross_tolerance")
    if result["cross"]["original_220"]["mismatch_pixels"]:
        result["failures"].append("NEEDS_FOREGROUND_REVIEW")
    # Early evidence lets the orchestrator honor the hard gate immediately.
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": args.model, "cross": result["cross"]["passed"],
                      "max_abs": result["cross"]["max_abs"], "outside": result["cross"]["outside_tolerance"]}), flush=True)
    if args.cross_only:
        result["status"] = "PASS_CROSS_ONLY" if not result["failures"] else "BLOCKED_CROSS"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if not result["failures"] else 2
    with SampleMemory() as infer_memory:
        result["structural_forward"] = []
        with torch.no_grad():
            for b, h, w in ((1, 256, 256), (2, 256, 256), (1, 256, 272)):
                logits = model(torch.zeros(b, 3, h, w))
                finite = bool(torch.isfinite(logits).all())
                assert tuple(logits.shape) == (b, 2, h, w) and finite
                result["structural_forward"].append({"shape": list(logits.shape), "finite": finite})
        layers = predict_layers(model, inputs["textured"])
        result["layers"] = {}
        for name, value in layers.items():
            array = value.numpy() if isinstance(value, torch.Tensor) else value
            assert np.isfinite(array).all()
            if name != "logits":
                assert array.shape[:2] == (220, 220)
            result["layers"][name] = {"shape": list(array.shape), "dtype": str(array.dtype), "finite": True}
        assert set(np.unique(layers["pred_mask"])) <= {0, 1}
        assert "error_map" not in layers
        assert 0 <= layers["probability"].min() <= layers["probability"].max() <= 1
        result["no_gt_metrics"] = "absent"
        from infer.pcb.visualize import error_map
        gt = layers["pred_mask"].copy()  # synthetic contract test, NOT an accuracy experiment
        gt[0, 0] = 1
        assert error_map(gt, layers["pred_mask"]).shape == (220, 220, 3)
        def forward():
            with torch.no_grad():
                return model(tensor)
        def full():
            with torch.no_grad():
                return to_numpy(*mask_and_probability(model(prepare_canvas(inputs["textured"]))))
        result["benchmark"] = {"warmup": args.warmup, "repeats": args.repeats,
            "forward": bench(forward, args.warmup, args.repeats),
            "full_pre_forward_post": bench(full, args.warmup, args.repeats),
            "cold_load_definition": "new process, includes weight hash, deserialize, construction; OS disk cache not flushed"}
    result["memory"]["inference_sampled_peak_rss_bytes"] = infer_memory.peak
    result["memory"]["after_inference"] = memory()
    with SampleMemory() as cam_memory:
        cam = SegmentationGradCAM(model)
        result["cam"] = {}
        for key, image in inputs.items():
            answer = cam(image)
            if "map" in answer:
                assert answer["map"].shape == (220, 220) and np.isfinite(answer["map"]).all()
                assert answer["status"] == "ok"
            if key == "textured" and answer["status"] != "ok":
                result["failures"].append("textured_cam:" + answer["status"])
            if key != "textured" and answer["status"] != "unavailable":
                result["failures"].append("empty_cam:" + key)
            result["cam"][key] = {k: v for k, v in answer.items() if k != "map"}
        result["benchmark"]["cam"] = bench(lambda: cam(inputs["textured"]), 1, max(3, args.repeats // 2))
        result["benchmark"]["cam_warmup"] = 1
        result["benchmark"]["cam_repeats"] = max(3, args.repeats // 2)
        assert len(cam.layer._forward_hooks) == len(cam.layer._backward_hooks) == 0
        assert all(p.grad is None for p in model.parameters())
    result["memory"]["cam_sampled_peak_rss_bytes"] = cam_memory.peak
    result["memory"]["after_cam"] = memory()
    result["memory"]["method"] = "GetProcessMemoryInfo; 10ms RSS sampling per phase; OS lifetime peak also reported. Each model in its own process."
    result["status"] = "VERIFIED_FOR_STAGING" if not result["failures"] else "BLOCKED"
    result["release_binding"] = {"manifest_sha256": MANIFEST_SHA256, "protocol_hash": PROTOCOL_HASH,
                                 "source_hashes": source_hashes(), "runtime": runtime_versions(),
                                 "checked_staged_file_hashes": len(frozen["files"])}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": args.model, "status": result["status"], "failures": result["failures"]}), flush=True)
    return 0 if not result["failures"] else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=tuple(MODELS))
    parser.add_argument("--assets", default=str(ASSET_ROOT))
    parser.add_argument("--output", default=str(ROOT / "docs/report/pcb-stage4-2026-10-29"))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--interop", type=int, default=None, help="Default preserves Worker runtime inter-op setting")
    parser.add_argument("--no-mkldnn", action="store_true")
    parser.add_argument("--cross-only", action="store_true")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.threads < 1 or args.warmup < 1 or args.repeats < 3:
        parser.error("threads>=1, warmup>=1 and repeats>=3 required")
    if args.model:
        return child(args)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    codes = {}
    for model_id in MODELS:
        command = [sys.executable, "-B", __file__, "--model", model_id, "--assets", args.assets,
                   "--output", str(output / f"{model_id}.json"), "--threads", str(args.threads),
                   "--warmup", str(args.warmup), "--repeats", str(args.repeats)]
        command += [flag for flag, enabled in (("--cross-only", args.cross_only), ("--no-mkldnn", args.no_mkldnn)) if enabled]
        if args.interop is not None:
            command += ["--interop", str(args.interop)]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=600,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
        (output / f"{model_id}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        print(run.stdout, end="", flush=True)
        if run.returncode not in (0, 2):
            print(run.stderr, flush=True)
        codes[model_id] = run.returncode
    (output / "process-exits.json").write_text(json.dumps(codes, indent=2), encoding="utf-8")
    if not args.cross_only:
        rows = {slug: json.loads((output / f"{slug}.json").read_text(encoding="utf-8")) for slug in MODELS}
        ok = all(codes[s] == 0 and rows[s].get("status") == "VERIFIED_FOR_STAGING" for s in MODELS)
        bindings = [r.get("release_binding") for r in rows.values()]
        ok = ok and all(b == bindings[0] and b is not None for b in bindings)
        receipt = {"status": "VERIFIED_FOR_STAGING" if ok else "BLOCKED",
                   "time_utc": datetime.now(timezone.utc).isoformat(),
                   "manifest_sha256": MANIFEST_SHA256, "protocol_hash": PROTOCOL_HASH,
                   "source_hashes": source_hashes(), "runtime": runtime_versions(),
                   "threads": args.threads, "interop": rows["unet"]["environment"]["interop"],
                   "mkldnn": not args.no_mkldnn, "models": {}}
        for slug, row in rows.items():
            receipt["models"][slug] = {"status": row.get("status"), "weight_sha256": MODELS[slug][0],
                "cross_passed": row["cross"]["passed"], "foreground_mismatch": row["cross"]["original_220"]["mismatch_pixels"],
                "structural_forward_passed": all(x["finite"] for x in row.get("structural_forward", [])) and len(row.get("structural_forward", [])) == 3,
                "layers_cam_passed": not row.get("failures") and bool(row.get("cam")),
                "evidence_file": str((output / f"{slug}.json").resolve())}
        target = receipt_path(args.assets)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)
    return 0 if all(code == 0 for code in codes.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
