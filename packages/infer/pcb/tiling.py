"""Bounded deployment adapter around the unchanged Meiwei 220-pixel protocol.

This module is Torch-free on import so API preflight and freezing remain cheap.
No resizing, GT, threshold changes, model training or CAM blending occur here.
"""
from hashlib import sha256
from pathlib import Path

TILE_SIZE = 220
STRIDE = 176
MAX_IMAGES = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_SIDE = 2048
MAX_PIXELS = MAX_SIDE * MAX_SIDE
MAX_WINDOW_MODEL_BUDGET = 500


def limits():
    return {"max_images": MAX_IMAGES, "max_image_bytes": MAX_IMAGE_BYTES,
            "max_batch_bytes": MAX_BATCH_BYTES, "max_side": MAX_SIDE,
            "max_pixels": MAX_PIXELS, "max_window_model_budget": MAX_WINDOW_MODEL_BUDGET,
            "tile_size": TILE_SIZE, "stride": STRIDE}


def source_hash():
    return sha256(Path(__file__).read_bytes()).hexdigest()


def assert_current_source():
    if source_hash() != _LOADED_SOURCE:
        raise ValueError("PCB tiling adapter changed; restart the process")


def _starts(length):
    last = max(length, TILE_SIZE) - TILE_SIZE
    starts = list(range(0, last + 1, STRIDE))
    if starts[-1] != last:
        starts.append(last)
    return starts


def plan(width, height, mode="RGB"):
    assert_current_source()
    if (type(width) is not int or type(height) is not int or min(width, height) < 1
            or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS or mode not in {"RGB", "L"}):
        raise ValueError("PCB input requires positive bounded dimensions and RGB/L 8-bit mode")
    xs, ys = _starts(width), _starts(height)
    native = width == height == TILE_SIZE
    adaptation = "none" if native else "sliding_window" if max(width, height) > TILE_SIZE else "pad_to_220"
    return {"schema": 1, "width": width, "height": height, "source_mode": mode,
            "input_adaptation": adaptation, "gray_to_rgb": mode == "L",
            "adapted": not native or mode == "L", "cam_supported": native and mode == "RGB",
            "tile_size": TILE_SIZE, "stride": STRIDE, "overlap": TILE_SIZE - STRIDE,
            "padding": {"right": max(0, TILE_SIZE-width), "bottom": max(0, TILE_SIZE-height), "value": 0},
            "x_starts": xs, "y_starts": ys, "windows": [[x, y] for y in ys for x in xs],
            "window_count": len(xs) * len(ys), "blend": "native" if native else "positive_cosine_floor_0.05",
            "position_rule": "stride_then_flush_last"}


def _predict_loaded(model, image_rgb):
    """Internal loaded-model entry, also used for deterministic numerical tests."""
    import numpy as np
    import torch
    from .preprocess import prepare_canvas
    from .postprocess import crop_source
    from .visualize import predict_layers, overlay, boundary, probability_heatmap

    image = np.asarray(image_rgb)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("tiling requires RGB uint8 after explicit input validation")
    height, width = image.shape[:2]
    meta = plan(width, height)
    if (height, width) == (TILE_SIZE, TILE_SIZE):
        # Exact old function, including logit argmax and every visualization.
        return predict_layers(model, image), meta
    canvas = np.pad(image, ((0, meta["padding"]["bottom"]), (0, meta["padding"]["right"]), (0, 0)),
                    mode="constant", constant_values=0)
    ch, cw = canvas.shape[:2]
    accum = np.zeros((2, ch, cw), dtype=np.float32)
    coverage = np.zeros((ch, cw), dtype=np.float32)
    axis = np.maximum(np.hanning(TILE_SIZE), .05).astype(np.float32)
    blend = axis[:, None] * axis[None, :]
    with torch.inference_mode():
        for x, y in meta["windows"]:
            logits = model(prepare_canvas(canvas[y:y+TILE_SIZE, x:x+TILE_SIZE]))
            if tuple(logits.shape) != (1, 2, 256, 256) or not bool(torch.isfinite(logits).all()):
                raise ValueError("invalid tile logits")
            probs = torch.softmax(crop_source(logits), dim=1)[0].cpu().numpy()
            if not np.isfinite(probs).all():
                raise ValueError("invalid tile probabilities")
            accum[:, y:y+TILE_SIZE, x:x+TILE_SIZE] += probs * blend[None]
            coverage[y:y+TILE_SIZE, x:x+TILE_SIZE] += blend
    denominator = coverage[:height, :width]
    if not np.isfinite(denominator).all() or np.any(denominator <= 0):
        raise ValueError("tile coverage has an uncovered pixel")
    probabilities = accum[:, :height, :width] / denominator[None]
    if (not np.isfinite(probabilities).all() or np.any(probabilities < 0)
            or np.any(probabilities > 1 + 1e-6) or not np.allclose(probabilities.sum(axis=0), 1, atol=1e-5, rtol=0)):
        raise ValueError("invalid fused probability distribution")
    # Tiny accumulation roundoff cannot escape the probability contract.
    probabilities = np.clip(probabilities, 0, 1)
    probabilities /= probabilities.sum(axis=0, keepdims=True)
    pred = probabilities.argmax(axis=0).astype(np.uint8)
    probability = probabilities[1]
    layers = {"pred_mask": pred, "probability": probability, "probabilities": probabilities,
              "probability_heatmap": probability_heatmap(probability), "overlay": overlay(image, pred),
              "boundary": boundary(pred)}
    meta = {**meta, "coverage_min": float(denominator.min()), "coverage_max": float(denominator.max())}
    return layers, meta


def predict_tiled(model_id, image_rgb, root=None):
    """One strict model load per child task; one bounded tile forward at a time."""
    import torch
    from .runtime import ROOT, load_model
    from .catalog import require_admitted

    assert_current_source()
    root = ROOT if root is None else root
    require_admitted(root)
    old_threads = torch.get_num_threads()
    try:
        model = load_model(model_id, root)
        result = _predict_loaded(model, image_rgb)
        assert_current_source()
        return result
    finally:
        torch.set_num_threads(old_threads)


def error_map(gt, pred):
    """Same legacy colors at original dimensions, without resampling GT."""
    import numpy as np
    gt, pred = np.asarray(gt), np.asarray(pred)
    if gt.ndim != 2 or gt.shape != pred.shape or set(np.unique(gt).tolist()) - {0, 1}:
        raise ValueError("GT must be binary and match the original image dimensions")
    canvas = np.zeros((*gt.shape, 3), dtype=np.uint8)
    canvas[(gt == 1) & (pred == 1)] = (40, 180, 70)
    canvas[(gt == 0) & (pred == 1)] = (220, 40, 40)
    canvas[(gt == 1) & (pred == 0)] = (40, 90, 220)
    return canvas


_LOADED_SOURCE = source_hash()
