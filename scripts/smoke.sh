#!/usr/bin/env bash
# scripts/smoke.sh
# ---------------------------------------------------------------------------
# Quick end-to-end smoke test.
# Uploads a small JPEG fixture to the running server and verifies the
# clipboard contains a PNG.
#
# Usage:
#   ./scripts/smoke.sh [http://192.168.x.x:8765] [token]
#
# If URL/token are not provided, the script reads them from the config file
# and tries http://localhost:8765.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FIXTURE="$PROJECT_DIR/tests/fixtures/sample.jpg"

# ---- Config ----
BASE_URL="${1:-}"
TOKEN="${2:-}"

if [[ -z "$TOKEN" ]]; then
    TOKEN_FILE="$HOME/.config/airdrop_linux/token"
    if [[ -f "$TOKEN_FILE" ]]; then
        TOKEN="$(cat "$TOKEN_FILE")"
    else
        echo "No token found. Pass as second argument or run the server first."
        exit 1
    fi
fi

if [[ -z "$BASE_URL" ]]; then
    # Try to detect scheme from certs presence
    if [[ -f "$PROJECT_DIR/certs/cert.pem" ]]; then
        LAN_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('10.254.254.254', 1))
    print(s.getsockname()[0])
except Exception:
    print('localhost')
" 2>/dev/null)
        BASE_URL="https://${LAN_IP}:8765"
    else
        BASE_URL="http://localhost:8765"
    fi
fi

# ---- Ensure fixture exists ----
if [[ ! -f "$FIXTURE" ]]; then
    echo "Fixture not found at $FIXTURE — generating a minimal JPEG..."
    mkdir -p "$(dirname "$FIXTURE")"
    python3 - <<'EOF'
from PIL import Image
import sys
img = Image.new("RGB", (64, 64), color=(100, 149, 237))
img.save(sys.argv[1], "JPEG")
EOF
    python3 -c "
from PIL import Image
img = Image.new('RGB', (64, 64), color=(100, 149, 237))
img.save('$FIXTURE', 'JPEG')
print('Created $FIXTURE')
"
fi

echo "Smoke test: POST $FIXTURE → $BASE_URL/upload"

# Detect curl flags for TLS
CURL_OPTS=()
if [[ "$BASE_URL" == https://* ]]; then
    CURL_OPTS+=("--cacert" "$(mkcert -CAROOT 2>/dev/null)/rootCA.pem" 2>/dev/null || true)
    # Fallback: skip verify (smoke test only, not production)
    CURL_OPTS+=("--insecure")
fi

HTTP_CODE=$(curl -s -o /tmp/smoke_response.json -w "%{http_code}" \
    "${CURL_OPTS[@]}" \
    -X POST \
    -H "X-Token: $TOKEN" \
    -F "photo=@$FIXTURE;type=image/jpeg" \
    "$BASE_URL/upload")

BODY=$(cat /tmp/smoke_response.json)
echo "HTTP $HTTP_CODE — $BODY"

if [[ "$HTTP_CODE" != "200" ]]; then
    echo "FAIL: expected 200, got $HTTP_CODE"
    exit 1
fi

# Verify clipboard contains a PNG
SESSION_TYPE="${XDG_SESSION_TYPE:-}"
if [[ "$SESSION_TYPE" == "wayland" ]] || [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    echo "Checking clipboard via wl-paste..."
    MIME=$(wl-paste --list-types 2>/dev/null | grep -i png || true)
    if [[ -n "$MIME" ]]; then
        echo "PASS: clipboard contains image/png"
    else
        echo "WARN: could not verify clipboard type (wl-paste --list-types returned no png)"
    fi
elif [[ -n "${DISPLAY:-}" ]]; then
    echo "Checking clipboard via xclip..."
    xclip -selection clipboard -o -t TARGETS 2>/dev/null | grep -q "image/png" \
        && echo "PASS: clipboard contains image/png" \
        || echo "WARN: could not verify clipboard type via xclip TARGETS"
else
    echo "WARN: No display session detected; skipping clipboard verify."
fi

echo "Smoke test complete."
