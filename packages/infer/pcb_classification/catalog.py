"""Torch-free identity/admission checks. Host administrators own private assets.

Full hashes are checked once per file-stat identity, not once per prediction.
Any stat/receipt/source change revalidates the complete frozen release and
changes the cache token. This is not a defence against a hostile OS administrator.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import threading
from copy import deepcopy
from pathlib import Path

PROTOCOL = "pcb_cls_deeppcb_roi_v0"
RELEASE = PROTOCOL + "_formal_v1"
ZIP_SHA = "bfb1c0ce379a47b5ac9acaa11c990042b1d75eddc99dfd55479a0f619316d8ba"
ZIP_BYTES = 20825269
MANIFEST_SHA = "7b2527efce91290c0da179481232b0ab24838bc75b992912ce2e1d386db9703b"
MODELS = {
    "efficientnet_b0": ("bb8a58511246651111cb6cb43c0c101fe20ba7d4de1633254c0432f03e039c39", 4015234, "EfficientNet-B0"),
    "mobilenet_v3_small": ("ea56cb4b3b2fd3be9d672b85780a07b1040556ea8acf07be4e9e7f20cb48b2f3", 1524006, "MobileNetV3-Small"),
}
DEFAULT = "efficientnet_b0"
THREADS, INTEROP = 2, 6
RECEIPT = ".windows-admission.json"
FILES = frozenset({"MANIFEST.json", "README.md", "stage4_handoff.md",
    "config/classes.json", "config/preprocess.json", "config/model_spec.json",
    "models/efficientnet_b0.pth", "models/mobilenet_v3_small.pth",
    "runtime/inference.py", "runtime/model_factory.py", "runtime/preprocess.py", "runtime/smoke_test.py",
    "validation/cpu_smoke_results.json", "validation/inference_consistency.json"})
_lock = threading.RLock()
_verified = {}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_hash():
    folder = Path(__file__).parent
    return hashlib.sha256(b"".join(name.encode() + b"\0" + (folder / name).read_bytes()
        for name in ("__init__.py", "catalog.py", "images.py", "runtime.py"))).hexdigest()


def runtime_identity():
    return {"python": platform.python_version(), "os": platform.system(), "machine": platform.machine(),
            "processor": platform.processor(),
            "libraries": {n: importlib.metadata.version(n) for n in ("torch", "torchvision", "numpy", "Pillow")},
            "threads": THREADS, "interop": INTEROP, "mkldnn": True, "device": "cpu", "dtype": "float32"}


def stat_identity(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("linked private asset")
    stat = path.stat()
    if not path.is_file():
        raise ValueError("not a regular asset")
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def verify_release(root):
    """Verify the fixed manifest and every payload; never execute package code."""
    root = Path(root).absolute()
    before = tuple((n, stat_identity(root / n)) for n in sorted(FILES))
    with _lock:
        if _verified.get(str(root), (None,))[0] == before:
            return deepcopy(_verified[str(root)][1])
        _verified.pop(str(root), None)
        if digest(root / "MANIFEST.json") != MANIFEST_SHA:
            raise ValueError("frozen manifest mismatch")
        manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
        entries = manifest["files"]
        if (manifest["protocol_id"] != PROTOCOL or manifest["asset_name"] != RELEASE
                or len(entries) != 13 or {r["path"] for r in entries} != FILES - {"MANIFEST.json"}):
            raise ValueError("frozen manifest coverage")
        for row in entries:
            path = root / row["path"]
            if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
                raise ValueError("frozen payload mismatch")
        configs = {n: json.loads((root / f"config/{n}.json").read_text(encoding="utf-8"))
                   for n in ("classes", "preprocess", "model_spec")}
        after = tuple((n, stat_identity(root / n)) for n in sorted(FILES))
        if after != before:
            raise ValueError("assets changed while verifying")
        result = {"configs": configs, "file_identity": before}
        _verified[str(root)] = (before, result)
        return deepcopy(result)


# Capture identity when modules are loaded, not on the first HTTP/job request.
# Updating code or installed libraries requires restarting long-lived processes.
_loaded_source = source_hash()
try:
    _loaded_runtime = runtime_identity()
except importlib.metadata.PackageNotFoundError:
    # API-only installations must still start and expose an unavailable catalog.
    _loaded_runtime = None


def admitted(root):
    verified = verify_release(root)
    code_hash = source_hash()
    current_runtime = runtime_identity()
    if code_hash != _loaded_source or current_runtime != _loaded_runtime:
        raise ValueError("deployment code changed; restart and readmit")
    path = Path(root) / RECEIPT
    receipt_stat = stat_identity(path)
    if receipt_stat[2] > 1000000:
        raise ValueError("oversized receipt")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or not isinstance(receipt.get("models"), dict):
        raise ValueError("invalid Windows admission structure")
    rows = receipt["models"]
    if (receipt.get("status") != "PASS" or receipt.get("protocol_id") != PROTOCOL
            or receipt.get("zip_sha256") != ZIP_SHA or receipt.get("manifest_sha256") != MANIFEST_SHA
            or receipt.get("source_hash") != code_hash or receipt.get("runtime") != current_runtime
            or receipt.get("tolerance") != {"atol": 0.001, "rtol": 0.0001}
            or set(rows) != set(MODELS)
            or any(not isinstance(rows[k], dict) or rows[k].get("passed") is not True
                   or rows[k].get("weight_sha256") != v[0]
                   or rows[k].get("strict") is not True or rows[k].get("weights_only") is not True
                   or type(rows[k].get("missing_keys")) is not int or rows[k]["missing_keys"] != 0
                   or type(rows[k].get("unexpected_keys")) is not int or rows[k]["unexpected_keys"] != 0
                   or type(rows[k].get("parameters")) is not int or rows[k]["parameters"] != v[1]
                   for k, v in MODELS.items())):
        raise ValueError("Windows admission missing or stale")
    if stat_identity(path) != receipt_stat:
        raise ValueError("receipt changed while reading")
    token = hashlib.sha256(repr((verified["file_identity"], receipt_stat, receipt, code_hash)).encode()).hexdigest()
    return {**verified, "source_hash": code_hash, "token": token, "receipt": receipt}


def catalog(root):
    try:
        proof = admitted(root)
    except (OSError, ValueError, KeyError, TypeError, importlib.metadata.PackageNotFoundError):
        proof = None
    return [{"model_id": key, "name": v[2], "params": v[1], "weight_sha256": v[0],
             "available": proof is not None, "default": key == DEFAULT,
             "protocol_id": PROTOCOL, "source_hash": proof["source_hash"] if proof else None}
            for key, v in MODELS.items()]
