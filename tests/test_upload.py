"""Integration tests for the /upload endpoint."""
from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import load_or_create_token


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def token():
    return load_or_create_token()


def _jpeg_bytes():
    from PIL import Image
    img = Image.new("RGB", (32, 32), (0, 100, 200))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_token_returns_401(self, client):
        resp = client.post(
            "/upload",
            files={"photo": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.post(
            "/upload?t=totally-wrong-token",
            files={"photo": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_token_via_query_param_accepted(self, client, token):
        with patch("app.main.copy_to_clipboard") as mock_clip:
            resp = client.post(
                f"/upload?t={token}",
                files={"photo": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        mock_clip.assert_called_once()

    def test_token_via_header_accepted(self, client, token):
        with patch("app.main.copy_to_clipboard") as mock_clip:
            resp = client.post(
                "/upload",
                headers={"X-Token": token},
                files={"photo": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        mock_clip.assert_called_once()


class TestRootRedirect:
    def test_root_without_token_redirects_to_tokenized_url(self, client, token):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/?t=" in resp.headers["location"]

    def test_root_with_ip_host_redirects_to_mdns_host(self, client, token):
        with patch("app.main.get_mdns_hostname", return_value="perryFile.local"):
            resp = client.get(
                f"/?t={token}",
                headers={"host": "172.20.10.4:8765"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("http://perryFile.local:8765/?t=")


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

class TestUploadValidation:
    def test_oversize_upload_returns_413(self, client, token):
        big = b"x" * (26 * 1024 * 1024)  # 26 MB
        resp = client.post(
            f"/upload?t={token}",
            files={"photo": ("big.jpg", big, "image/jpeg")},
        )
        assert resp.status_code == 413

    def test_corrupt_image_returns_422(self, client, token):
        resp = client.post(
            f"/upload?t={token}",
            files={"photo": ("bad.jpg", b"not an image", "image/jpeg")},
        )
        assert resp.status_code == 422

    def test_valid_jpeg_returns_200(self, client, token):
        with patch("app.main.copy_to_clipboard"):
            resp = client.post(
                f"/upload?t={token}",
                files={"photo": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTextUpload:
    def test_text_upload_missing_token_returns_401(self, client):
        resp = client.post("/upload-text", json={"text": "hello"})
        assert resp.status_code == 401

    def test_text_upload_empty_returns_422(self, client, token):
        resp = client.post(f"/upload-text?t={token}", json={"text": "   "})
        assert resp.status_code == 422

    def test_text_upload_success_returns_200(self, client, token):
        with patch("app.main.copy_text_to_clipboard") as mock_copy:
            resp = client.post(f"/upload-text?t={token}", json={"text": "hello from phone"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_copy.assert_called_once_with("hello from phone")

    def test_text_upload_clipboard_error_returns_503(self, client, token):
        from app.clipboard import ClipboardError

        with patch("app.main.copy_text_to_clipboard", side_effect=ClipboardError("clipboard failed")):
            resp = client.post(f"/upload-text?t={token}", json={"text": "hello"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Clipboard failure
# ---------------------------------------------------------------------------

class TestClipboardFailure:
    def test_clipboard_error_returns_503(self, client, token):
        from app.clipboard import ClipboardError

        with patch(
            "app.main.copy_to_clipboard",
            side_effect=ClipboardError("wl-copy not found"),
        ):
            resp = client.post(
                f"/upload?t={token}",
                files={"photo": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 503
        assert "wl-copy" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
