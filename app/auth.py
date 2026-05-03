"""Token-based authentication for local network use."""
import hmac
import os
import secrets
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "airdrop_linux"
_TOKEN_FILE = _CONFIG_DIR / "token"

# In-process cache so we read disk once per run
_cached_token: str | None = None


def load_or_create_token() -> str:
    """Load the persistent token from disk, creating it if absent."""
    global _cached_token
    if _cached_token is not None:
        return _cached_token

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text().strip()
        if len(token) >= 32:
            _cached_token = token
            return _cached_token

    # Generate new token
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(token)
    _TOKEN_FILE.chmod(0o600)
    _cached_token = token
    return _cached_token


def rotate_token() -> str:
    """Generate and persist a new token, invalidating any existing QR codes."""
    global _cached_token
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(token)
    _TOKEN_FILE.chmod(0o600)
    _cached_token = token
    return _cached_token


def verify_token(provided: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    expected = load_or_create_token()
    return hmac.compare_digest(expected.encode(), provided.encode())
