"""Tests for app/clipboard.py — session detection and tool dispatch."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.clipboard import ClipboardError, _detect_session, copy_text_to_clipboard, copy_to_clipboard


class TestDetectSession:
    def test_wayland_from_xdg(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        assert _detect_session() == "wayland"

    def test_x11_from_xdg(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        assert _detect_session() == "x11"

    def test_wayland_from_display_var(self, monkeypatch):
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.delenv("DISPLAY", raising=False)
        assert _detect_session() == "wayland"

    def test_x11_from_display_var(self, monkeypatch):
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        assert _detect_session() == "x11"

    def test_no_session_raises(self, monkeypatch):
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        with pytest.raises(ClipboardError):
            _detect_session()


class TestCopyToClipboard:
    def _make_popen_mock(self, returncode=None):
        """Return a mock Popen process that looks like a running wl-copy holder."""
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = b""
        # poll() returns None = still running (normal wl-copy steady state)
        proc.poll.return_value = returncode
        return proc

    def test_wayland_calls_wl_copy(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        proc = self._make_popen_mock(returncode=None)  # stays running

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/wl-copy"), \
             patch("app.clipboard.subprocess.Popen", return_value=proc) as mock_popen:
            copy_to_clipboard(b"fakepng")

        cmd = mock_popen.call_args[0][0]
        assert cmd[0].endswith("wl-copy")
        assert "--type" in cmd
        assert "image/png" in cmd
        # Data was written to stdin
        proc.stdin.write.assert_called_once_with(b"fakepng")
        proc.stdin.close.assert_called_once()

    def test_x11_calls_xclip(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/xclip"), \
             patch("app.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr=b"")
            copy_to_clipboard(b"fakepng")

        cmd = mock_run.call_args[0][0]
        assert cmd[0].endswith("xclip")
        assert "-selection" in cmd
        assert "clipboard" in cmd
        assert "image/png" in cmd

    def test_missing_tool_raises(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        with patch("app.clipboard.shutil.which", return_value=None):
            with pytest.raises(ClipboardError, match="not found"):
                copy_to_clipboard(b"fakepng")

    def test_wayland_nonzero_returncode_raises(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

        proc = self._make_popen_mock(returncode=1)

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/wl-copy"), \
             patch("app.clipboard.subprocess.Popen", return_value=proc):
            with pytest.raises(ClipboardError, match="exited with code 1"):
                copy_to_clipboard(b"fakepng")

    def test_x11_nonzero_returncode_raises(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/xclip"), \
             patch("app.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b"some error")
            with pytest.raises(ClipboardError, match="exited with code 1"):
                copy_to_clipboard(b"fakepng")

    def test_wayland_text_calls_wl_copy(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        proc = self._make_popen_mock(returncode=None)

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/wl-copy"), \
             patch("app.clipboard.subprocess.Popen", return_value=proc) as mock_popen:
            copy_text_to_clipboard("hello world")

        cmd = mock_popen.call_args[0][0]
        assert cmd[0].endswith("wl-copy")
        assert "text/plain;charset=utf-8" in cmd
        proc.stdin.write.assert_called_once_with(b"hello world")

    def test_x11_text_calls_xclip(self, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        with patch("app.clipboard.shutil.which", return_value="/usr/bin/xclip"), \
             patch("app.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr=b"")
            copy_text_to_clipboard("hello text")

        cmd = mock_run.call_args[0][0]
        assert cmd[0].endswith("xclip")
        assert "text/plain" in cmd
        assert mock_run.call_args[1]["input"] == b"hello text"

    def test_windows_text_calls_powershell(self, monkeypatch):
        monkeypatch.setattr("app.clipboard.sys.platform", "win32")

        with patch("app.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr=b"")
            copy_text_to_clipboard("hello windows")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "powershell"
