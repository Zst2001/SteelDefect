"""Opt-in true-weight synthetic background/thin-line visual checks, never accuracy.

Writes full-size original/output PNGs and review montages into a NEW directory.
Does not connect to services, read .env, or change frozen sources/weights/receipts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages")]


def main():
    if sys.flags.optimize:
        raise RuntimeError("Visual acceptance requires assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    out = parser.parse_args().output
    if out.exists():
        raise RuntimeError("Choose a new evidence directory")
    out.mkdir(parents=True)

    def offline(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(args[0])).name.lower().startswith(".env"):
                raise RuntimeError("Visual verification forbids .env")
        if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            raise RuntimeError("Visual verification forbids external IO")
    sys.addaudithook(offline)

    import numpy as np
    import torch
    import cv2
    from PIL import Image, ImageDraw
    from infer.pcb.runtime import ROOT as assets, MODELS, load_model
    from infer.pcb.catalog import require_admitted, source_hashes, receipt_path
    from infer.pcb.tiling import _predict_loaded, source_hash, assert_current_source, plan

    torch.set_num_threads(2)
    torch.set_num_interop_threads(6)
    cv2.setNumThreads(1)
    require_admitted(assets)
    frozen = source_hashes()
    receipt_sha = hashlib.sha256(receipt_path(assets).read_bytes()).hexdigest()
    adapter_sha = source_hash()
    width, height = 512, 384
    input_plan = plan(width, height)
    assert input_plan["x_starts"] == [0, 176, 292] and input_plan["y_starts"] == [0, 164]
    plain = np.full((height, width, 3), (25, 80, 35), dtype=np.uint8)
    sparse = plain.copy()
    # One-pixel crossing lines, isolated 3x3 targets, and last-row/column targets.
    sparse[192, 150:330] = (235, 220, 165)
    sparse[130:240, 300] = (235, 220, 165)
    sparse[162:165, 174:177] = (220, 80, 40)
    sparse[218:221, 290:293] = (220, 80, 40)
    sparse[380:384, 511] = (235, 220, 165)
    sparse[383, 508:512] = (235, 220, 165)
    cases = {"pure-background": plain, "sparse-thin-lines": sparse}
    x_seams = sorted({x for start in input_plan["x_starts"] for x in (start, start + 220) if 0 < x < width})
    y_seams = sorted({y for start in input_plan["y_starts"] for y in (start, start + 220) if 0 < y < height})
    report = {"status": "RUNNING", "scope": "True CPU weights; synthetic visual QA only; NOT accuracy evaluation",
              "timing": "Functional pass, may overlap other CPU checks; not a benchmark",
              "adapter_source_hash": adapter_sha, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "input_plan": input_plan, "tile_start_or_end_x": x_seams, "tile_start_or_end_y": y_seams,
              "sparse_source_changed_pixels": int(np.any(sparse != plain, axis=2).sum()),
              "frozen_sources_before": frozen, "receipt_sha256_before": receipt_sha, "runs": []}
    try:
        for case, image in cases.items():
            Image.fromarray(image).save(out / f"{case}-original.png")
            guide = Image.fromarray(image)
            draw = ImageDraw.Draw(guide)
            for x in x_seams:
                draw.line((x, 0, x, height - 1), fill=(80, 140, 240))
            for y in y_seams:
                draw.line((0, y, width - 1, y), fill=(80, 140, 240))
            guide.save(out / f"{case}-window-guide-not-input.png")
        for slug in MODELS:
            model = load_model(slug, assets)
            for case, image in cases.items():
                assert_current_source()
                start = time.perf_counter()
                layers, meta = _predict_loaded(model, image)
                elapsed = time.perf_counter() - start
                assert_current_source()
                assert meta["window_count"] == 6 and meta["coverage_min"] > 0
                for key in ("pred_mask", "probability"):
                    assert layers[key].shape == (height, width) and np.isfinite(layers[key]).all()
                assert set(np.unique(layers["pred_mask"])) <= {0, 1}
                probability = layers["probability"]
                assert np.all(probability >= 0) and np.all(probability <= 1)
                np.testing.assert_allclose(layers["probabilities"].sum(axis=0), 1, atol=1e-6, rtol=0)
                stem = f"{slug}-{case}"
                Image.fromarray(layers["pred_mask"]).save(out / f"{stem}-pred-mask-01.png")
                panels = [("Original: synthetic", image), ("Mask: display 0/255", layers["pred_mask"] * 255)]
                for key in ("overlay", "boundary", "probability_heatmap"):
                    assert layers[key].shape == (height, width, 3) and layers[key].dtype == np.uint8
                    Image.fromarray(layers[key]).save(out / f"{stem}-{key}.png")
                    panels.append((key, layers[key]))
                np.save(out / f"{stem}-defect-probability.npy", probability, allow_pickle=False)
                montage = Image.new("RGB", (5 * (width + 8), height + 76), "white")
                draw = ImageDraw.Draw(montage)
                for index, (title, array) in enumerate(panels):
                    x = index * (width + 8)
                    draw.text((x + 4, 4), title, fill="#173450")
                    montage.paste(Image.fromarray(array).convert("RGB"), (x + 4, 28))
                draw.text((4, height + 34), f"SYNTHETIC QA ONLY / NOT ACCURACY | {slug} | {case} | output pixels 1:1 | x starts [0,176,292], y starts [0,164]", fill="#173450")
                draw.text((4, height + 52), "Separate blue window-guide is only a review overlay, never model input. No GT or accuracy metrics.", fill="#173450")
                montage.save(out / f"{stem}-montage.png")
                # Pixel discontinuity observations are diagnostics, not quality acceptance thresholds.
                jump_x = np.abs(np.diff(probability, axis=1))
                jump_y = np.abs(np.diff(probability, axis=0))
                row = {"model_id": slug, "case": case, "elapsed_seconds": elapsed,
                       "width": width, "height": height, "window_count": 6,
                       "coverage_min": meta["coverage_min"], "full_size_layers": True,
                       "finite_normalized_probabilities": True, "foreground_pixels": int(layers["pred_mask"].sum()),
                       "probability_min": float(probability.min()), "probability_max": float(probability.max()),
                       "max_adjacent_jump_all_x": float(jump_x.max()), "max_adjacent_jump_all_y": float(jump_y.max()),
                       "max_adjacent_jump_at_window_x": float(jump_x[:, np.array(x_seams) - 1].max()),
                       "max_adjacent_jump_at_window_y": float(jump_y[np.array(y_seams) - 1, :].max()),
                       "montage": f"{stem}-montage.png", "prediction": f"{stem}-pred-mask-01.png"}
                report["runs"].append(row)
                print(f"{slug} {case}: full-size PASS, 6 windows, fg={row['foreground_pixels']}, {elapsed:.3f}s", flush=True)
            del model
        assert source_hash() == adapter_sha and source_hashes() == frozen
        assert hashlib.sha256(receipt_path(assets).read_bytes()).hexdigest() == receipt_sha
        require_admitted(assets)
        report["frozen_sources_and_receipt_unchanged"] = True
        report["status"] = "PASS"
    finally:
        (out / "visual.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("PASS: six true-weight synthetic visual cases; inspect PNGs for model-dependent edge artifacts", flush=True)


if __name__ == "__main__":
    main()
