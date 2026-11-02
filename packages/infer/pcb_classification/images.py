"""Bounded input decoding without Torch; exact original L/224 pixels retained."""
import io
import warnings
from pathlib import PurePosixPath

from PIL import Image

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
ADAPTATION = "已按冻结协议转换为 224×224 灰度图；训练集准确率不保证适用于此图。"


def decode(content, filename, mime=None):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("图片须为 1 字节至 2 MiB")
    # Reject client-supplied paths rather than sanitizing them into plausible names.
    if (not filename or filename != PurePosixPath(filename).name or any(c in filename for c in '\\:\x00')
            or filename.endswith((".", " "))):
        raise ValueError("图片名称不能包含路径")
    suffix = PurePosixPath(filename).suffix.lower()
    fmt = "PNG" if content.startswith(b"\x89PNG\r\n\x1a\n") else "JPEG" if content.startswith(b"\xff\xd8\xff") else None
    if (fmt is None or suffix not in ({".png"} if fmt == "PNG" else {".jpg", ".jpeg"})
            or mime is not None and mime != {"PNG": "image/png", "JPEG": "image/jpeg"}[fmt]):
        raise ValueError("文件内容、扩展名与 MIME 必须为一致的 PNG/JPEG")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                if (image.format != fmt or getattr(image, "n_frames", 1) != 1 or image.mode not in {"L", "RGB", "RGBA", "P", "CMYK"}
                        or image.width * image.height > MAX_PIXELS or min(image.size) < 1
                        or image.getexif().get(274, 1) != 1):
                    raise ValueError("须为静态 8 位 PNG/JPEG，像素不超过 4096²，EXIF 方向须为 1 或缺省")
                image.load()
                native = fmt == "PNG" and image.mode == "L" and image.size == (224, 224)
                meta = {"format": fmt, "mode": image.mode, "width": image.width, "height": image.height,
                        "bytes": len(content), "input_adapted": not native,
                        "adaptation_notice": ADAPTATION if not native else None}
                gray = image.copy() if image.mode == "L" else image.convert("L")
                if gray.size != (224, 224):
                    gray = gray.resize((224, 224), Image.Resampling.BILINEAR)
                return gray, meta
        except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ValueError("无法解码图片或图片超出安全限制") from exc
