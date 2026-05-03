"""Image conversion pipeline: any supported input → PNG bytes (in memory)."""
from __future__ import annotations

import io

from PIL import Image, ImageOps

# Register HEIC/HEIF opener once at import time.
# pillow-heif may not be installed; we handle that gracefully.
try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:
    _HEIF_AVAILABLE = False

# Hard limits
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_DIMENSION_PX = 8000


class ImageError(ValueError):
    """Raised for invalid or unsupported image data."""


def to_clipboard_image(raw: bytes) -> tuple[bytes, str]:
    """Prepare *raw* image bytes for the clipboard, returning (data, mime_type).

    JPEG inputs are kept as JPEG (with EXIF orientation applied) for speed —
    no lossless re-encode, no format inflation.  Everything else (HEIC, WebP,
    PNG with bad mode, etc.) is converted to PNG.

    Applies EXIF orientation, strips metadata, caps dimensions.
    Never writes to disk.

    Raises:
        ImageError: if the data is not a recognised image or exceeds limits.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError(
            f"Upload too large: {len(raw) / 1_048_576:.1f} MB "
            f"(max {MAX_UPLOAD_BYTES // 1_048_576} MB)"
        )

    try:
        buf = io.BytesIO(raw)
        img: Image.Image = Image.open(buf)
        img.load()  # force decode so format errors surface here
    except Exception as exc:
        raise ImageError(f"Could not decode image: {exc}") from exc

    input_format = (img.format or "").upper()

    # Enforce dimension cap
    if img.width > MAX_DIMENSION_PX or img.height > MAX_DIMENSION_PX:
        raise ImageError(
            f"Image too large: {img.width}×{img.height} px "
            f"(max {MAX_DIMENSION_PX} px in either dimension)"
        )

    # Apply EXIF orientation so rotated phone shots paste upright
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # non-fatal; ignore if EXIF is malformed

    if input_format == "JPEG" and img.mode in ("RGB", "L"):
        # Fast path: re-encode as JPEG to preserve orientation fix.
        # quality=95 is visually lossless for a one-step re-encode.
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=95)
        return out.getvalue(), "image/jpeg"

    # Slow path: normalise and export as PNG.
    if img.mode not in ("RGB", "RGBA"):
        if img.mode in ("P", "PA", "LA", "RGBA"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=False)
    return out.getvalue(), "image/png"


def to_png_bytes(raw: bytes) -> bytes:
    """Legacy helper: convert *raw* to PNG bytes (used by tests)."""
    data, _ = to_clipboard_image(raw)
    if data[:3] == b"\xff\xd8\xff":  # JPEG magic — convert to PNG for callers
        buf = io.BytesIO(data)
        img = Image.open(buf)
        img.load()
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=False)
        return out.getvalue()
    return data


def heif_available() -> bool:
    return _HEIF_AVAILABLE
