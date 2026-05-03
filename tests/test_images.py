"""Tests for app/images.py"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.images import ImageError, MAX_UPLOAD_BYTES, to_png_bytes


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestToPngBytes:
    def test_jpeg_converts_to_png(self, sample_jpeg):
        result = to_png_bytes(sample_jpeg)
        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    def test_png_passthrough(self, sample_png):
        result = to_png_bytes(sample_png)
        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    def test_output_is_bytes(self, sample_jpeg):
        result = to_png_bytes(sample_jpeg)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_png_header(self, sample_jpeg):
        result = to_png_bytes(sample_jpeg)
        # PNG magic bytes: 8950 4e47
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_rgba_png_preserved(self):
        """RGBA PNG stays RGBA."""
        import io as _io
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
        buf = _io.BytesIO()
        img.save(buf, "PNG")
        result = to_png_bytes(buf.getvalue())
        out = Image.open(_io.BytesIO(result))
        assert out.mode == "RGBA"

    def test_palette_mode_converted(self):
        """Palette (P) mode images convert without error."""
        import io as _io
        img = Image.new("RGB", (16, 16), (0, 128, 255)).convert("P")
        buf = _io.BytesIO()
        img.save(buf, "PNG")
        result = to_png_bytes(buf.getvalue())
        assert result[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestToPngBytesErrors:
    def test_corrupt_data_raises(self):
        with pytest.raises(ImageError):
            to_png_bytes(b"this is not an image")

    def test_empty_bytes_raises(self):
        with pytest.raises(ImageError):
            to_png_bytes(b"")

    def test_oversize_upload_raises(self):
        oversized = b"x" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ImageError, match="too large"):
            to_png_bytes(oversized)

    def test_oversized_dimensions_raises(self):
        """Images larger than MAX_DIMENSION_PX should be rejected."""
        import io as _io
        from app.images import MAX_DIMENSION_PX
        img = Image.new("RGB", (MAX_DIMENSION_PX + 1, 10), (0, 0, 0))
        buf = _io.BytesIO()
        img.save(buf, "PNG")
        with pytest.raises(ImageError, match="too large"):
            to_png_bytes(buf.getvalue())
