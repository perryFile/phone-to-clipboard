"""Generate test fixtures once, then reuse."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
import app.main as _main_module


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear in-process rate-limit state before each test so tests are isolated."""
    _main_module._rate_buckets.clear()
    yield
    _main_module._rate_buckets.clear()

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_jpeg(width: int = 64, height: int = 64, color=(100, 149, 237)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _make_png(width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGBA", (width, height), color=(0, 200, 100, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="session", autouse=True)
def create_fixtures():
    """Write fixture files to disk once per test session."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    jpeg_path = FIXTURES_DIR / "sample.jpg"
    if not jpeg_path.exists():
        jpeg_path.write_bytes(_make_jpeg())

    png_path = FIXTURES_DIR / "sample.png"
    if not png_path.exists():
        png_path.write_bytes(_make_png())


@pytest.fixture()
def sample_jpeg() -> bytes:
    return _make_jpeg()


@pytest.fixture()
def sample_png() -> bytes:
    return _make_png()
