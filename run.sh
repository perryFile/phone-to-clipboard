#!/usr/bin/env bash
# Run the airdrop-linux server in development mode.
# Usage: ./run.sh [--rotate-token] [--host HOST] [--port PORT]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual env if present
if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

CERT_DIR="$SCRIPT_DIR/certs"
KEYFILE="$CERT_DIR/key.pem"
CERTFILE="$CERT_DIR/cert.pem"

if [[ -f "$KEYFILE" && -f "$CERTFILE" ]]; then
    exec python -m app.main \
        --ssl-keyfile "$KEYFILE" \
        --ssl-certfile "$CERTFILE" \
        "$@"
else
    echo "⚠  No TLS certs found in $CERT_DIR — running over plain HTTP."
    echo "   Run scripts/setup-mkcert.sh to generate trusted certs."
    exec python -m app.main "$@"
fi
