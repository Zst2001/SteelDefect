"""Opt-in Windows CPU tiling verification; synthetic inputs, no accuracy claim.

Never alters frozen payloads/admission, production services, .env or datasets.
Run --output with a new evidence directory. Large dimensions are measured once,
not presented as a percentile benchmark or as an HTTP/queue latency promise.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages"), str(ROOT / "scripts")]


def main():
    if sys.flags.optimize:
        raise RuntimeError("CPU acceptance requires assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output
    if out.exists(): raise RuntimeError("Choose a new evidence directory")
    out.mkdir(parents=True)
    machine = platform.platform()
    cpu = platform.processor()
    def offline(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(args[0])).name.lower().startswith(".env"):
                raise RuntimeError("CPU tiling verification forbids .env")
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            raise RuntimeError("CPU tiling verification forbids external IO")
    sys.addaudithook(offline)
    import numpy as np
    import torch
    import cv2
    from PIL import Image, ImageDraw
    from check_pcb_cpu import memory, SampleMemory, compare_logits, reference_inputs
    from infer.pcb.runtime import ROOT as assets, MODELS, load_model
    from infer.pcb.catalog import require_admitted, source_hashes, runtime_versions, receipt_path
    from infer.pcb.visualize import predict_layers
    from infer.pcb.tiling import _predict_loaded, source_hash, plan, limits
    torch.set_num_threads(2)
    torch.set_num_interop_threads(6)
    cv2.setNumThreads(1)
    assert machine.startswith("Windows") and torch.backends.mkldnn.enabled
    require_admitted(assets)
    frozen_sources = source_hashes()
    receipt_sha = hashlib.sha256(receipt_path(assets).read_bytes()).hexdigest()
    report = {"status": "RUNNING", "scope": "real strict-loaded Windows CPU, synthetic data, no accuracy evaluation",
              "runtime": runtime_versions(), "platform": machine, "cpu": cpu, "threads": 2, "interop": 6,
              "mkldnn": True, "limits": limits(), "adapter_source_hash": source_hash(),
              "frozen_sources_before": frozen_sources, "receipt_sha256_before": receipt_sha,
              "timing": "one measured resident-model pass per size; decode/HTTP/queue/save excluded; model load separate",
              "models": {}, "runs": []}
    try:
        reference = reference_inputs()["textured"]
        np.testing.assert_array_equal(reference, np.load(assets / "reference_vectors/input_220_rgb.npy", allow_pickle=False))
        sizes = [(110, 110), (220, 220), (221, 300), (512, 384), (1024, 1024), (2048, 220), (2048, 2048)]
        for slug in MODELS:
            start = time.perf_counter()
            model = load_model(slug, assets)
            load_ms = (time.perf_counter()-start)*1000
            old = predict_layers(model, reference)
            native, _ = _predict_loaded(model, reference)
            keys = sorted(old)
            equal = {key: bool(np.array_equal(np.asarray(old[key]), np.asarray(native[key]))) for key in keys}
            assert all(equal.values())
            expected = np.load(assets / f"reference_vectors/{slug}_logits.npy", allow_pickle=False)
            cross = compare_logits(native["logits"].numpy(), expected)
            assert cross["passed"] and cross["original_220"]["mismatch_pixels"] == 0
            report["models"][slug] = {"load_ms": load_ms, "weight_sha256": MODELS[slug][0],
                "strict": True, "weights_only": True, "parameters": sum(p.numel() for p in model.parameters()),
                "old_vs_new_bitwise": equal, "frozen_reference": f"reference_vectors/{slug}_logits.npy", "cross": cross}
            for width, height in sizes:
                yy, xx = np.indices((height, width))
                image = np.stack(((xx*3+yy*7)%256, (xx*11+yy*2)%256, (xx*5+yy*13)%256), axis=2).astype(np.uint8)
                # Sparse high-contrast lines at boundaries are only synthetic QA.
                image[175:178, :] = (220, 50, 30)
                image[:, 351:354] = (30, 220, 50)
                image[-1] = 255
                image[:, -1] = 255
                with SampleMemory() as measured:
                    start = time.perf_counter()
                    layers, meta = _predict_loaded(model, image)
                    elapsed_ms = (time.perf_counter()-start)*1000
                for key in ("pred_mask", "probability"):
                    assert layers[key].shape == (height, width) and np.isfinite(layers[key]).all()
                for key in ("overlay", "boundary", "probability_heatmap"):
                    assert layers[key].shape == (height, width, 3) and layers[key].dtype == np.uint8
                assert set(np.unique(layers["pred_mask"])) <= {0, 1}
                assert np.all(layers["probability"] >= 0) and np.all(layers["probability"] <= 1)
                if "probabilities" in layers:
                    np.testing.assert_allclose(layers["probabilities"].sum(axis=0), 1, atol=1e-6, rtol=0)
                    assert meta["coverage_min"] > 0
                row = {"model_id": slug, "width": width, "height": height, "window_count": meta["window_count"],
                       "elapsed_ms": elapsed_ms, "load_plus_inference_ms": load_ms+elapsed_ms,
                       "sampled_peak_rss_bytes": measured.peak, "memory_after": memory(),
                       "full_size_layers": True, "finite_probability": True, "plan": meta,
                       "foreground_pixels": int(layers["pred_mask"].sum()), "below_120_seconds": load_ms+elapsed_ms < 120000}
                assert row["below_120_seconds"], "Reduce per-child budget before acceptance"
                report["runs"].append(row)
                print(f"{slug} {width}x{height}: {meta['window_count']} windows, {elapsed_ms/1000:.3f}s, RSS peak {measured.peak/1048576:.1f} MiB", flush=True)
                if (width, height) in {(221, 300), (512, 384), (2048, 2048)}:
                    panels = [("Original (synthetic)", image), ("Overlay", layers["overlay"]),
                              ("Boundary", layers["boundary"]), ("Defect probability", layers["probability_heatmap"])]
                    montage = Image.new("RGB", (1200, 340), "#ffffff")
                    draw = ImageDraw.Draw(montage)
                    for index, (label, array) in enumerate(panels):
                        view = Image.fromarray(array); view.thumbnail((290, 280))
                        montage.paste(view, (index*300+5, 35))
                        draw.text((index*300+5, 8), label, fill="#173450")
                    draw.text((5, 320), f"SYNTHETIC QA ONLY / NOT ACCURACY | {slug} | original {width}x{height} | evidence thumbnails only", fill="#173450")
                    montage.save(out / f"{slug}-{width}x{height}-synthetic.png")
                del layers, image
            del model
        assert source_hashes() == frozen_sources
        assert hashlib.sha256(receipt_path(assets).read_bytes()).hexdigest() == receipt_sha
        require_admitted(assets)
        report["frozen_sources_and_receipt_unchanged"] = True
        report["status"] = "PASS"
    finally:
        (out / "cpu.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"PASS: {len(report['runs'])} true CPU size/model runs; all native layers bitwise equal", flush=True)


if __name__ == "__main__": main()
