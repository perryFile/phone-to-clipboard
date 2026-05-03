#!/usr/bin/env bash
# scripts/setup-mkcert.sh
# ---------------------------------------------------------------------------
# Generate a locally-trusted TLS certificate for airdrop-linux using mkcert.
#
# What this does:
#   1. Installs mkcert if not already present (via apt or direct download).
#   2. Installs the local CA into the system trust store.
#   3. Creates certs/key.pem + certs/cert.pem for the LAN IP + hostname.
#
# After running this script, follow the printed instructions to install the
# mkcert root CA on your iPhone once.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CERT_DIR="$PROJECT_DIR/certs"

mkdir -p "$CERT_DIR"

# ---- 1. Ensure mkcert is available ----
if ! command -v mkcert &>/dev/null; then
    echo "mkcert not found. Attempting to install..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq mkcert
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y mkcert
    elif command -v brew &>/dev/null; then
        brew install mkcert
    else
        echo ""
        echo "Could not auto-install mkcert."
        echo "Download it from: https://github.com/FiloSottile/mkcert/releases"
        echo "Place the binary in your PATH as 'mkcert' and re-run this script."
        exit 1
    fi
fi

echo "mkcert: $(command -v mkcert)"

# ---- 2. Install the local CA ----
mkcert -install
echo ""
echo "Local CA installed into system trust store."

# ---- 3. Detect LAN IP ----
LAN_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('10.254.254.254', 1))
    print(s.getsockname()[0])
except Exception:
    print('')
finally:
    s.close()
" 2>/dev/null || true)

HOSTNAME=$(hostname)
DOMAINS="localhost 127.0.0.1 ::1 $HOSTNAME"
if [[ -n "$LAN_IP" ]]; then
    DOMAINS="$DOMAINS $LAN_IP"
    echo "Detected LAN IP: $LAN_IP"
fi

# ---- 4. Generate cert ----
pushd "$CERT_DIR" > /dev/null
# shellcheck disable=SC2086
mkcert -key-file key.pem -cert-file cert.pem $DOMAINS
popd > /dev/null

echo ""
echo "================================================================"
echo "  Certificates written to: $CERT_DIR"
echo ""
echo "  NEXT STEP — Trust this CA on your iPhone:"
echo ""
echo "  1. Find the CA file:"
echo "     $(mkcert -CAROOT)/rootCA.pem"
echo ""
echo "  2. Transfer it to your iPhone (AirDrop, e-mail, or run:"
echo "       python3 -m http.server 8080 --directory \"\$(mkcert -CAROOT)\""
echo "     then open http://$LAN_IP:8080/rootCA.pem in Safari)."
echo ""
echo "  3. On iPhone: Settings → General → VPN & Device Management"
echo "     → tap the profile → Install."
echo ""
echo "  4. Settings → General → About → Certificate Trust Settings"
echo "     → enable the mkcert root CA."
echo ""
echo "  After that, your iPhone will trust the airdrop-linux certificate."
echo "================================================================"
