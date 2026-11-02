"""Standard-library-only PCB admission gate. No Torch/API imports or enable flag.

The immutable manifest hash anchors every staged payload file to the verified
release. A sibling receipt is produced only by explicit three-model validation.
"""
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform

from .runtime import MODELS, ROOT, THREADS

MANIFEST_SHA256 = "fdb601a391a178ab6a761b4562945771807e511d990c5824727a2ac00fba9cf6"
SUMS_SHA256 = "aad5646e163b0f03cbce2b79357fb741ef7a206396d66cc361330903d0aedb41"
NAMES = {"unet": "U-Net", "unet_resnet18": "ResNet18-U-Net", "unetpp_resnet18": "ResNet18-U-Net++"}
PROTOCOL = {"scene": "pcb", "task_kind": "segmentation", "release": "pcb_seg_meiwei_v2_formal_v1",
            "classes": ["background", "defect"], "input_rgb": [220, 220, 3], "dtype": "uint8",
            "pad": [18, 18, 18, 18], "pad_value": 0, "scale": "float32/255",
            "crop": [18, 238, 18, 238], "prediction": "argmax_dim1", "probability": "softmax_dim1_channel1"}
SOURCE_FILES = ("models.py", "preprocess.py", "postprocess.py", "visualize.py", "runtime.py", "catalog.py")
INTEROP = 6  # Actual configured Worker runtime; changing it requires re-admission.


class PcbAdmissionError(ValueError):
    pass


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


PROTOCOL_HASH = canonical_hash(PROTOCOL)


def runtime_versions():
    return {"python": platform.python_version(), **{n: version(n) for n in (
        "torch", "torchvision", "numpy", "Pillow", "opencv-python-headless")}}


def source_hashes():
    base = Path(__file__).parent
    return {name: sha256((base / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def _safe_file(base: Path, relative: str):
    path = base / relative
    if not path.is_file() or any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                                 for p in (path, *path.parents)):
        raise PcbAdmissionError("PCB 准入文件缺失或路径不安全")
    if not path.resolve().is_relative_to(base.resolve()):
        raise PcbAdmissionError("PCB 准入文件超出私有目录")
    return path


def verify_staging(root=ROOT):
    root = Path(root).absolute()
    manifest_path = _safe_file(root, "ASSET_MANIFEST.json")
    data = manifest_path.read_bytes()
    if sha256(data).hexdigest() != MANIFEST_SHA256:
        raise PcbAdmissionError("PCB 固定发行清单指纹不一致")
    manifest = json.loads(data)
    files = {row["path"]: row for row in manifest["files"]}
    if len(files) != 50 or len(manifest["files"]) != 50:
        raise PcbAdmissionError("PCB 清单文件集合不完整")
    for name, row in files.items():
        path = _safe_file(root, name)
        if path.stat().st_size != row["bytes"]:
            raise PcbAdmissionError("PCB 准入文件体积不一致")
        with path.open("rb") as stream:
            digest = sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise PcbAdmissionError("PCB 准入文件 SHA-256 不一致")
    expected = set(files) | {"ASSET_MANIFEST.json", "SHA256SUMS.txt"}
    observed = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if observed != expected:
        raise PcbAdmissionError("PCB 准入文件集合被修改")
    sums_bytes = _safe_file(root, "SHA256SUMS.txt").read_bytes()
    if sha256(sums_bytes).hexdigest() != SUMS_SHA256:
        raise PcbAdmissionError("PCB 校验清单指纹被修改")
    sums = sums_bytes.decode("utf-8")
    wanted = {name: row["sha256"] for name, row in files.items()} | {"ASSET_MANIFEST.json": MANIFEST_SHA256}
    pairs = [line.split("  ", 1) for line in sums.splitlines() if line]
    if len(pairs) != 51 or {name: digest for digest, name in pairs} != wanted:
        raise PcbAdmissionError("PCB 内部校验清单不一致")
    return {name: row["sha256"] for name, row in files.items()}


def receipt_path(root=ROOT):
    root = Path(root).absolute()
    return root.parent / (root.name + ".admission.json")


def require_admitted(root=ROOT):
    try:
        verify_staging(root)
        path = receipt_path(root)
        _safe_file(path.parent, path.name)
        if path.stat().st_size > 100_000:
            raise PcbAdmissionError("PCB 准入记录过大")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (receipt.get("status") != "VERIFIED_FOR_STAGING" or receipt.get("manifest_sha256") != MANIFEST_SHA256
                or receipt.get("protocol_hash") != PROTOCOL_HASH or receipt.get("source_hashes") != source_hashes()
                or receipt.get("runtime") != runtime_versions() or receipt.get("threads") != THREADS
                or receipt.get("interop") != INTEROP or receipt.get("mkldnn") is not True
                or set(receipt.get("models", {})) != set(MODELS)):
            raise PcbAdmissionError("PCB 需要在当前 Worker 环境重新准入")
        for slug, identity in MODELS.items():
            item = receipt["models"][slug]
            if (item.get("status") != "VERIFIED_FOR_STAGING" or item.get("weight_sha256") != identity[0]
                    or item.get("cross_passed") is not True or item.get("foreground_mismatch") != 0
                    or item.get("structural_forward_passed") is not True or item.get("layers_cam_passed") is not True):
                raise PcbAdmissionError("三个 PCB 模型尚未全部通过准入")
        return receipt
    except PcbAdmissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        raise PcbAdmissionError("PCB 准入记录不可用，请联系管理员") from exc


def catalog(root=ROOT):
    try:
        require_admitted(root)
        reason = None
    except PcbAdmissionError as exc:
        reason = str(exc)
    deployment_hash = canonical_hash(source_hashes())
    return [{"slug": slug, "name": NAMES[slug], "available": reason is None,
             "status": "available" if reason is None else "unavailable", "reason": reason,
             "param_count": item[1], "weight_sha256": item[0], "protocol_hash": PROTOCOL_HASH,
             "asset_hash": canonical_hash({"model": slug, "weights": item[0], "protocol": PROTOCOL_HASH,
                                           "manifest": MANIFEST_SHA256, "deployment_source": deployment_hash}),
             "deployment_source_hash": deployment_hash,
             "scene": "pcb", "task_kind": "segmentation"} for slug, item in MODELS.items()]
