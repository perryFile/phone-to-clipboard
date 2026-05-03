"""Tests for app/auth.py"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch


def test_load_or_create_returns_string():
    from app.auth import load_or_create_token
    token = load_or_create_token()
    assert isinstance(token, str)
    assert len(token) >= 32


def test_token_persistent_across_calls():
    from app.auth import load_or_create_token
    t1 = load_or_create_token()
    t2 = load_or_create_token()
    assert t1 == t2


def test_rotate_token_changes_value():
    from app import auth
    original = auth.load_or_create_token()
    rotated = auth.rotate_token()
    assert rotated != original
    # Subsequent load returns the rotated token
    assert auth.load_or_create_token() == rotated
    # Restore original so other tests aren't affected
    auth._cached_token = original


def test_verify_token_correct():
    from app.auth import load_or_create_token, verify_token
    token = load_or_create_token()
    assert verify_token(token) is True


def test_verify_token_wrong():
    from app.auth import verify_token
    assert verify_token("wrong-token") is False


def test_verify_token_empty():
    from app.auth import verify_token
    assert verify_token("") is False


def test_token_file_permissions():
    """Token file must be readable only by owner (mode 0o600)."""
    from app.auth import _TOKEN_FILE, load_or_create_token
    load_or_create_token()
    if _TOKEN_FILE.exists():
        mode = _TOKEN_FILE.stat().st_mode & 0o777
        assert mode == 0o600, f"Token file mode is {oct(mode)}, expected 0o600"
