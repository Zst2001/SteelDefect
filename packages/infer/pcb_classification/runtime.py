"""Trusted CPU execution, one resident model per process, no upload imports."""
import io
import json
import threading

import numpy as np
import PIL
import torch
import torchvision
from torch import nn
from torchvision import models

from .catalog import DEFAULT, INTEROP, MODELS, PROTOCOL, THREADS, admitted, stat_identity, verify_release
from .images import decode

_lock = threading.RLock()
_cache = None


def clear_cache():
    global _cache
    with _lock:
        _cache = None


def build_model(model_id):
    if model_id == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None)
        model.classifier[1] = nn.Linear(1280, 6)
    elif model_id == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=None)
        model.classifier[3] = nn.Linear(1024, 6)
    else:
        raise ValueError("unknown PCB classification model")
    return model.cpu().float()


def strict_load(model_id, root):
    verify_release(root)
    model = build_model(model_id)
    path = root / f"models/{model_id}.pth"
    before = stat_identity(path)
    state = torch.load(path, map_location="cpu", weights_only=True)
    report = model.load_state_dict(state, strict=True)
    if report.missing_keys or report.unexpected_keys or before != stat_identity(path):
        raise ValueError("strict weight identity failed")
    if sum(p.numel() for p in model.parameters()) != MODELS[model_id][1]:
        raise ValueError("parameter count changed")
    return model.eval()


def tensor_from_gray(gray, config):
    x = np.asarray(gray, dtype=np.float32) / np.float32(255.0)
    x = (x - np.float32(config["mean"])) / np.float32(config["std"])
    return torch.from_numpy(x).unsqueeze(0).repeat(3, 1, 1).contiguous().unsqueeze(0)


def checked_output(logits, model_id, classes, meta):
    if logits.shape != (1, 6) or not torch.isfinite(logits).all():
        raise ValueError("invalid classification logits")
    probs = torch.softmax(logits, dim=1)[0]
    if not torch.isfinite(probs).all() or (probs < 0).any() or (probs > 1).any() or abs(float(probs.sum()) - 1) > 1e-5:
        raise ValueError("invalid classification probabilities")
    index = int(probs.argmax())
    result = {"protocol_id": PROTOCOL, "model_id": model_id, **classes[index],
              "confidence": float(probs[index]), "probabilities": probs.tolist(), **meta}
    json.dumps(result, allow_nan=False)
    return result


def predict(root, model_id, content, filename, *, enabled=True):
    global _cache
    with _lock:
        if not enabled or model_id not in MODELS:
            clear_cache()
            raise ValueError("PCB classification disabled or unknown model")
        try:
            proof = admitted(root)
            loaded = {"torch": str(torch.__version__), "torchvision": torchvision.__version__,
                      "numpy": np.__version__, "Pillow": PIL.__version__}
            if loaded != proof["receipt"]["runtime"]["libraries"]:
                raise ValueError("loaded libraries differ from admission; restart and readmit")
            if torch.get_num_interop_threads() != INTEROP or not torch.backends.mkldnn.enabled:
                raise ValueError("CPU policy differs from admission")
        except Exception:
            clear_cache()
            raise
        old_threads = torch.get_num_threads()
        try:
            torch.set_num_threads(THREADS)
            key = (str(root.absolute()), model_id, proof["token"])
            hit = _cache is not None and _cache[0] == key
            if not hit:
                clear_cache()
                _cache = (key, strict_load(model_id, root))
            gray, meta = decode(content, filename)
            x = tensor_from_gray(gray, proof["configs"]["preprocess"])
            with torch.inference_mode():
                logits = _cache[1](x)
                result = checked_output(logits, model_id, proof["configs"]["classes"]["classes"], meta)
            if admitted(root)["token"] != proof["token"]:
                clear_cache()
                raise ValueError("admission changed during prediction")
            result["cache_hit"] = hit
            preview = io.BytesIO()
            gray.save(preview, format="PNG")
            return result, preview.getvalue()
        except Exception:
            # Also drop the resident model when post-inference revalidation fails.
            clear_cache()
            raise
        finally:
            torch.set_num_threads(old_threads)
