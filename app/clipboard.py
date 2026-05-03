"""Copy PNG bytes to the system clipboard (Windows, Wayland, or X11)."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import time


class ClipboardError(RuntimeError):
    """Raised when the clipboard write fails."""


def _detect_session() -> str:
    """Return 'windows', 'wayland', 'x11', or raise ClipboardError."""
    if sys.platform == "win32":
        return "windows"

    # Prefer explicit session type env var
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type == "wayland":
        return "wayland"
    if session_type == "x11":
        return "x11"

    # Fall back to presence of display vars
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"

    raise ClipboardError(
        "Could not determine display session type. "
        "Neither WAYLAND_DISPLAY nor DISPLAY is set. "
        "Make sure you are running inside a graphical session."
    )


def _require_tool(name: str) -> str:
    """Return path to *name* or raise ClipboardError with install hint."""
    path = shutil.which(name)
    if path is None:
        hints = {
            "wl-copy": "sudo apt install wl-clipboard   # or: sudo dnf install wl-clipboard",
            "xclip": "sudo apt install xclip           # or: sudo dnf install xclip",
        }
        hint = hints.get(name, f"Please install {name}")
        raise ClipboardError(
            f"Required tool '{name}' not found in PATH.\n{hint}"
        )
    return path


def copy_to_clipboard(image_bytes: bytes, mime_type: str = "image/png") -> None:
    """Pipe *image_bytes* into the system clipboard with the given *mime_type*.

    Wayland: wl-copy is intentionally kept alive in the background to hold the
    clipboard selection — it only exits when something else copies. We use
    Popen + a short startup check instead of run() so we don't kill it.

    X11: xclip exits immediately after copying, so run() is fine.

    Raises:
        ClipboardError: if the session type is unknown, a required tool is
            missing, or the subprocess returns a non-zero exit code.
    """
    session = _detect_session()

    if session == "windows":
        _copy_windows(image_bytes, mime_type)
    elif session == "wayland":
        _copy_wayland(image_bytes, mime_type)
    else:
        _copy_x11(image_bytes, mime_type)


def copy_text_to_clipboard(text: str) -> None:
    """Copy *text* into the system clipboard as plain text."""
    session = _detect_session()

    if session == "windows":
        _copy_text_windows(text)
    elif session == "wayland":
        _copy_text_wayland(text)
    else:
        _copy_text_x11(text)


def _copy_windows(image_bytes: bytes, mime_type: str = "image/png") -> None:
    """Use PowerShell (built-in on every Windows install) to set the clipboard image."""
    b64 = base64.b64encode(image_bytes).decode()
    if mime_type == "image/jpeg":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            f"$bytes = [Convert]::FromBase64String('{b64}');"
            "$ms = New-Object System.IO.MemoryStream(,$bytes);"
            "$img = [System.Drawing.Image]::FromStream($ms);"
            "[System.Windows.Forms.Clipboard]::SetImage($img);"
            "$ms.Dispose();"
            "$img.Dispose()"
        )
    else:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            f"$bytes = [Convert]::FromBase64String('{b64}');"
            "$ms = New-Object System.IO.MemoryStream(,$bytes);"
            "$img = [System.Drawing.Image]::FromStream($ms);"
            "[System.Windows.Forms.Clipboard]::SetImage($img);"
            "$ms.Dispose();"
            "$img.Dispose()"
        )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(f"PowerShell clipboard timed out: {exc}") from exc
    except OSError as exc:
        raise ClipboardError(f"Failed to run PowerShell: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ClipboardError(
            f"PowerShell exited with code {result.returncode}: {stderr}"
        )


def _copy_text_windows(text: str) -> None:
    """Use PowerShell to set clipboard text on Windows."""
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    script = (
        f"$bytes = [Convert]::FromBase64String('{b64}');"
        "$txt = [System.Text.Encoding]::UTF8.GetString($bytes);"
        "Set-Clipboard -Value $txt"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(f"PowerShell clipboard timed out: {exc}") from exc
    except OSError as exc:
        raise ClipboardError(f"Failed to run PowerShell: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ClipboardError(
            f"PowerShell exited with code {result.returncode}: {stderr}"
        )


def _copy_wayland(image_bytes: bytes, mime_type: str = "image/png") -> None:
    """Use wl-copy, letting it stay alive in the background as a clipboard holder."""
    tool = _require_tool("wl-copy")
    cmd = [tool, "--type", mime_type]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Write the image and close stdin so wl-copy knows input is done
        proc.stdin.write(image_bytes)
        proc.stdin.close()

        # Give it up to 3 s to either confirm it started OK or fail fast.
        # wl-copy normally stays running (exit code never comes) — that is correct.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            rc = proc.poll()
            if rc is None:
                # Still running — good, it's holding the clipboard.
                return
            if rc == 0:
                # Exited cleanly (unusual but acceptable).
                return
            # Non-zero exit — real error
            stderr = proc.stderr.read().decode(errors="replace").strip()
            raise ClipboardError(
                f"wl-copy exited with code {rc}: {stderr}"
            )
            break
        # Still running after 3 s — this is the normal steady state.
        # Don't kill it; leave it holding the clipboard.

    except OSError as exc:
        raise ClipboardError(f"Failed to start wl-copy: {exc}") from exc


def _copy_x11(image_bytes: bytes, mime_type: str = "image/png") -> None:
    """Use xclip, which exits as soon as the data is placed on the clipboard."""
    tool = _require_tool("xclip")
    cmd = [tool, "-selection", "clipboard", "-t", mime_type, "-i"]

    try:
        result = subprocess.run(
            cmd,
            input=image_bytes,
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(f"xclip timed out: {exc}") from exc
    except OSError as exc:
        raise ClipboardError(f"Failed to run xclip: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ClipboardError(
            f"xclip exited with code {result.returncode}: {stderr}"
        )


def _copy_text_wayland(text: str) -> None:
    """Use wl-copy to hold plain text in Wayland clipboard."""
    tool = _require_tool("wl-copy")
    cmd = [tool, "--type", "text/plain;charset=utf-8"]
    text_bytes = text.encode("utf-8")

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        proc.stdin.write(text_bytes)
        proc.stdin.close()

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            rc = proc.poll()
            if rc is None:
                return
            if rc == 0:
                return
            stderr = proc.stderr.read().decode(errors="replace").strip()
            raise ClipboardError(f"wl-copy exited with code {rc}: {stderr}")
    except OSError as exc:
        raise ClipboardError(f"Failed to start wl-copy: {exc}") from exc


def _copy_text_x11(text: str) -> None:
    """Use xclip for plain text on X11."""
    tool = _require_tool("xclip")
    cmd = [tool, "-selection", "clipboard", "-t", "text/plain", "-i"]

    try:
        result = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(f"xclip timed out: {exc}") from exc
    except OSError as exc:
        raise ClipboardError(f"Failed to run xclip: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise ClipboardError(f"xclip exited with code {result.returncode}: {stderr}")


def session_type() -> str:
    """Public accessor for the detected session type string."""
    return _detect_session()
