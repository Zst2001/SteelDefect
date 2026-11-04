"""Adapt common upload formats before the separately admitted ROI decoder.

The worker continues to consume the frozen PNG/JPEG contract. Source provenance
is kept separately; image facts always describe the bytes actually frozen.
"""
from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import PurePosixPath

from PIL import Image, ImageOps

from infer.pcb_classification.images import MAX_PIXELS, decode

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP", "BMP", "TIFF", "GIF")
SUPPORTED_MODES = {"1", "L", "LA", "RGB", "RGBA", "P", "CMYK"}


def prepare_upload(content: bytes, filename: str):
    """Return frozen bytes, frozen decoder facts, and original-file provenance.

    Browser MIME and the suffix are hints, not proof of file content. Never
    use the client filename as a storage path, even after image verification.
    """
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("请选择非空图片，单张不超过 10 MiB")
    if (not filename or filename != PurePosixPath(filename).name
            or any(c in filename for c in '\\:\x00')
            or any(ord(c) < 32 for c in filename) or filename.endswith((".", " "))):
        raise ValueError("图片名称不能包含路径或控制字符")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(content)) as image:
                _validate(image)
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                _validate(image)
                image.load()
                orientation = image.getexif().get(274, 1)
                if orientation not in range(1, 9):
                    raise ValueError("图片方向信息无效，请重新导出图片")
                source = {"filename": filename[:128], "format": image.format, "mode": image.mode,
                          "width": image.width, "height": image.height, "bytes": len(content),
                          "sha256": hashlib.sha256(content).hexdigest(), "normalized": False,
                          "orientation_applied": orientation != 1, "conversion_notice": None}
                # Keep old PNG/JPEG bytes and all decoder facts unchanged. A
                # safe content-derived name also permits absent/wrong suffixes.
                if image.format in {"PNG", "JPEG"}:
                    canonical_name = "image.png" if image.format == "PNG" else "image.jpg"
                    try:
                        _, facts = decode(content, canonical_name)
                        return content, facts, source
                    except ValueError:
                        pass  # Safe, verified new inputs are adapted below.
                oriented = ImageOps.exif_transpose(image)
                gray = oriented.copy() if oriented.mode == "L" else oriented.convert("L")
                if gray.size != (224, 224):
                    gray = gray.resize((224, 224), Image.Resampling.BILINEAR)
                # Equal RGB channels preserve the exact grayscale bytes while
                # making the frozen decoder correctly mark this as adapted.
                stream = io.BytesIO()
                gray.convert("RGB").save(stream, format="PNG")
                frozen = stream.getvalue()
                _, facts = decode(frozen, "image.png")
                source["normalized"] = True
                source["conversion_notice"] = (
                    ("已校正图片方向；" if orientation != 1 else "")
                    + "已将上传图片转换为 224×224 灰度等价输入，按既有分类协议处理。")
                return frozen, facts, source
        except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ValueError("无法解码图片或图片超出安全限制，请重新导出后上传") from exc


def _validate(image):
    if image.format not in SUPPORTED_FORMATS:
        raise ValueError("支持 PNG、JPEG、WebP、BMP、TIFF 与 GIF 静态图片")
    if image.width * image.height > MAX_PIXELS or min(image.size) < 1:
        raise ValueError("图像总像素不能超过 4096²，请缩小或裁剪后上传")
    if getattr(image, "n_frames", 1) != 1:
        raise ValueError("暂不支持动画或多页图片，请导出所需的一张静态图像")
    if image.mode not in SUPPORTED_MODES:
        raise ValueError("暂不支持 16 位或浮点图像，请导出为普通 8 位图像")
