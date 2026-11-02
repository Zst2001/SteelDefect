"""Independent Pillow/NumPy/DB verification of browser-downloaded evidence.

Deliberately does not call the production metrics or inference functions.
"""
import base64
import hashlib
import io
import json

import numpy as np
from PIL import Image, ImageDraw


def make_inputs(output):
    # Generated from geometry and deterministic random texture, never a dataset
    # image, reference-vector file, model prediction, or real ground truth.
    rng = np.random.RandomState(20261030)
    pixels = rng.randint(15, 70, size=(220, 220, 3), dtype=np.uint8)
    board = Image.fromarray(pixels)
    draw = ImageDraw.Draw(board)
    for y in (28, 60, 98, 138, 185):
        draw.line([(12, y), (105, y), (105, y + 18), (205, y + 18)], fill=(188, 157, 92), width=6)
    for x, y in ((35, 28), (175, 78), (60, 138), (185, 203)):
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(211, 202, 161), outline=(38, 61, 48), width=3)
    draw.rectangle((89, 52, 117, 112), fill=(11, 18, 19))
    draw.line((135, 118, 179, 159), fill=(230, 226, 194), width=4)
    gt = np.zeros((220, 220), dtype=np.uint8)
    gt[51:69, 88:121] = 255
    gt[120:160, 147:154] = 255
    gt[182:198, 40:78] = 255
    source_dir = output / "synthetic-inputs"
    source_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for key, fmt, filename in (("png-gt", "PNG", "synthetic-pcb-220.png"), ("jpeg-no-gt", "JPEG", "synthetic-pcb-220.jpg")):
        stream = io.BytesIO()
        board.save(stream, format=fmt, **({"quality": 91, "subsampling": 0} if fmt == "JPEG" else {}))
        content = stream.getvalue()
        (source_dir / filename).write_bytes(content)
        row = {"key": key, "filename": filename, "mime": "image/png" if fmt == "PNG" else "image/jpeg",
               "imageBase64": base64.b64encode(content).decode(), "hasGT": key == "png-gt"}
        if row["hasGT"]:
            stream = io.BytesIO()
            Image.fromarray(gt).save(stream, format="PNG")
            (source_dir / "synthetic-pcb-gt.png").write_bytes(stream.getvalue())
            row["gtBase64"] = base64.b64encode(stream.getvalue()).decode()
        cases.append(row)
    (source_dir / "provenance.json").write_text(json.dumps({
        "source": "Procedural RGB board geometry and RandomState(20261030) texture; artificial binary GT rectangles",
        "purpose": "Synthetic integration and metric arithmetic only; not model accuracy evidence",
        "size": [220, 220], "gt_positive_pixels": int(np.count_nonzero(gt)),
        "gt_negative_pixels": int(gt.size - np.count_nonzero(gt)),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.iterdir() if p.is_file()},
    }, indent=2), encoding="utf-8")
    return cases


def verify_results(output, settings, SessionLocal):
    from app.db.models import Artifact, MetricSet, Sample, Task
    from app.services.storage import resolve_uri
    browser = json.loads((output / "results.json").read_text(encoding="utf-8"))
    checks, runs = [], []
    def check(condition, message):
        if not condition:
            raise AssertionError(message)
        checks.append(message)
    def image_at(path):
        content = path.read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            return content, image.format, image.mode, image.size, np.asarray(image).copy()
    try:
        check(browser["status"] == "PASS", "browser completed both real tasks")
        check(len(browser["createdTasks"]) == 2, "exactly two U-Net tasks created")
        with SessionLocal() as db:
            check(db.query(Task).count() == 2, "isolated database contains exactly the two submitted tasks")
            for row in browser["createdTasks"]:
                task_id, key = row["taskId"], row["key"]
                task = db.get(Task, task_id)
                sample = db.query(Sample).filter_by(version_id=task.dataset_version_id).one()
                metric = db.query(MetricSet).filter_by(task_id=task_id).one_or_none()
                folder = output / key
                source = output / "synthetic-inputs" / row["filename"]
                uploaded, source_format, mode, size, source_array = image_at(source)
                saved = resolve_uri(sample.origin_uri, settings).read_bytes()
                check(saved == uploaded, f"{key}: Sample preserves exact uploaded bytes")
                sha = hashlib.sha256(uploaded).hexdigest()
                check(sample.sha256 == sha == row["api"]["samples"][0]["sha256"], f"{key}: upload, Sample and API SHA-256 agree")
                origin, origin_format, origin_mode, origin_size, origin_array = image_at(folder / "origin.png")
                check(origin.startswith(b"\x89PNG\r\n\x1a\n") and origin_format == "PNG", f"{key}: origin is genuine PNG")
                check(origin_mode == mode == "RGB" and origin_size == size == (220, 220), f"{key}: source and origin preserve RGB 220 dimensions")
                check(np.array_equal(source_array, origin_array), f"{key}: origin equals Pillow-decoded model input without rotation or rescaling")
                if source_format == "JPEG":
                    check(uploaded.startswith(b"\xff\xd8\xff"), "JPEG input has genuine JPEG magic")
                    with Image.open(source) as image:
                        check(image.getexif().get(274, 1) == 1, "JPEG has default EXIF orientation")
                raw = image_at(folder / "pred_mask.png")[4]
                visual = image_at(folder / "mask_visual.png")[4]
                check(raw.shape == visual.shape == (220, 220), f"{key}: both masks retain 220 coordinates")
                check(set(np.unique(raw)) <= {0, 1} and set(np.unique(visual)) <= {0, 255}, f"{key}: raw and visual mask values satisfy 0/1 and 0/255 contracts")
                check(np.array_equal(raw != 0, visual != 0), f"{key}: raw and visual foreground locations identical")
                if row["api"]["cam"]["status"] == "unavailable":
                    check(not np.any(raw), f"{key}: unavailable CAM corresponds to an actually empty downloaded prediction")
                # A model may legitimately predict no foreground on synthetic
                # data. Positive and empty display cases have deterministic unit
                # coverage; the live run records its actual foreground below.
                result = json.loads((folder / "pcb.json").read_text(encoding="utf-8"))
                check(result["foreground_pixels"] == int(np.count_nonzero(raw)), f"{key}: result foreground count matches downloaded mask")
                db_artifacts = db.query(Artifact).filter_by(task_id=task_id).all()
                check({a.kind for a in db_artifacts} == {a["kind"] for a in row["api"]["artifacts"]}, f"{key}: DB and API artifact sets identical")
                independent = None
                if row["hasGT"]:
                    truth = image_at(folder / "gt.png")[4]
                    check(set(np.unique(truth)) == {0, 1}, "GT download contains positive and negative binary pixels")
                    input_gt = image_at(output / "synthetic-inputs/synthetic-pcb-gt.png")[4]
                    check(np.array_equal(truth > 0, input_gt > 0), "GT download foreground equals independent synthetic upload")
                    positive, target = raw.astype(bool), truth.astype(bool)
                    tp = int(np.count_nonzero(positive & target))
                    fp = int(np.count_nonzero(positive & ~target))
                    fn = int(np.count_nonzero(~positive & target))
                    tn = int(np.count_nonzero(~positive & ~target))
                    divide = lambda a, b: a / b if b else None
                    independent = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                        "defect_dice": divide(2*tp, 2*tp+fp+fn), "iou": divide(tp, tp+fp+fn),
                        "precision": divide(tp, tp+fp), "recall": divide(tp, tp+fn)}
                    check(tp + fp + fn + tn == 220*220, "independent confusion matrix covers all pixels")
                    check(metric is not None and metric.n == 1 and metric.scope == "pcb_uploaded_pair", "real DB MetricSet present with correct scope")
                    for label, observed in (("DB MetricSet", metric.payload_json), ("API", row["api"]["metrics"]), ("pcb.json", result["metrics"])):
                        for field, expected in independent.items():
                            actual = observed[field]
                            check(actual is None if expected is None else actual is not None and abs(actual - expected) < 1e-12,
                                  f"{label} {field} equals independent downloaded mask/GT calculation")
                    for field, label in (("defect_dice", "Defect Dice"), ("iou", "Defect IoU"), ("precision", "Precision"), ("recall", "Recall")):
                        expected = "—" if independent[field] is None else f"{independent[field] * 100:.2f}%"
                        check(row["uiMetrics"][label] == expected, f"UI {label} equals independent rounded percentage")
                    check(row["uiCounts"] == f"TP {tp} · FP {fp} · FN {fn} · TN {tn}（像素）", "UI confusion matrix equals independent counts")
                else:
                    check(metric is None, "no-GT task has no database MetricSet")
                    check(result["metrics"] == row["api"]["metrics"] == {"available": False}, "no-GT JSON and API contain no fabricated metrics")
                runs.append({"key": key, "task_id": task_id, "sample_id": sample.id, "source_format": source_format,
                    "upload_sha256": sha, "sample_sha256": hashlib.sha256(saved).hexdigest(),
                    "origin_format": origin_format, "origin_mode": origin_mode, "origin_size": origin_size,
                    "origin_magic_hex": origin[:8].hex(), "pixels_equal_decoded_source": True,
                    "raw_mask_values": np.unique(raw).tolist(), "visual_mask_values": np.unique(visual).tolist(),
                    "foreground_pixels": int(np.count_nonzero(raw)), "independent_metrics": independent,
                    "db_metrics": metric.payload_json if metric else None})
        result = {"status": "PASS", "checks": len(checks), "assertions": checks, "runs": runs}
    except Exception as exc:
        result = {"status": "FAIL", "checks": len(checks), "assertions": checks, "runs": runs, "error": str(exc)}
        (output / "independent-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    (output / "independent-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "PASS", "independent_checks": len(checks), "report": str(output / "independent-verification.json")}
