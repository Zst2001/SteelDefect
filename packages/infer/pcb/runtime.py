"""Fixed-identity CPU loader for explicit offline PCB admission.

Importing this catalog does not import Torch or execute any assets. The website
does not register this module until all three models pass the stage-4 gate.
"""
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "assets/pcb/meiwei_v2_formal_v1"
MODELS = {
    "unet": ("c9ffbb31c5bc80ef74b71d5b35a1d13517610656362a2030bae639156314235b", 7849634, "dec1"),
    "unet_resnet18": ("6ce8f3ebe139c6781670af1889c1c80e519980ab056964a97b2359a1c7366fcd", 14413570, "dec0"),
    "unetpp_resnet18": ("ff621b6e9d6097f7f8d89bc12bc37834c94c3e68aa190b99cffa22c7cbf2bd69", 16111106, "dec0"),
}
SCENE = "pcb"
TASK_KIND = "segmentation"
CLASSES = ("background", "defect")
ENABLED = False
THREADS = 2


def load_model(model_id: str, root: Path = ROOT, *, threads: int = THREADS):
    if model_id not in MODELS:
        raise ValueError("PCB model is outside the reviewed allowlist")
    import torch
    from .models import build_model
    from .catalog import INTEROP
    if torch.get_num_interop_threads() != INTEROP or not torch.backends.mkldnn.enabled:
        raise ValueError("PCB CPU execution settings differ from the admitted Worker environment")

    # Match the validated CPU budget on the shared single-job Worker. Do not
    # reset inter-op pools here: PyTorch only permits changing those once.
    if threads not in (1, 2):
        raise ValueError("PCB CPU thread budget must be 1 or 2")
    torch.set_num_threads(threads)
    expected_hash, params, layer = MODELS[model_id]
    base = Path(root).absolute()
    path = base / "models" / model_id / "weights.pth"
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
           for p in (base, path.parent.parent, path.parent, path)):
        raise ValueError("PCB weight path must not traverse links")
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("PCB weight path escapes private assets")
    with path.open("rb") as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("PCB weight SHA-256 mismatch")
        stream.seek(0)
        state = torch.load(stream, map_location="cpu", weights_only=True)
    if not isinstance(state, dict) or not state or any(
        not isinstance(k, str) or not isinstance(v, torch.Tensor) for k, v in state.items()
    ):
        raise ValueError("PCB weights must be a tensor state_dict")
    model = build_model(model_id, num_classes=2, in_channels=3)
    incompatible = model.load_state_dict(state, strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ValueError("PCB strict loading returned incompatible keys")
    if sum(p.numel() for p in model.parameters()) != params or model.cam_layer_name != layer:
        raise ValueError("PCB model identity mismatch")
    return model.cpu().eval()
