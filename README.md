# phone-to-clipboard

Send photos and text from your phone browser directly to your Linux (or Windows) clipboard — no app, no cloud, LAN-only.

Point your phone camera at the QR code, tap the shutter button, and the image lands in your clipboard ready to Ctrl+V.

---

## How it works

1. A FastAPI server runs on your desktop.
2. Your phone opens the web UI in its browser (no app install needed).
3. You take a photo or type text and hit send.
4. The server writes it straight to your clipboard.

---

## Requirements

- Python 3.11+
- Linux: `wl-clipboard` (Wayland) **or** `xclip` (X11)
- Windows: nothing extra — PowerShell is used

Install system clipboard tool if needed:

```bash
# Wayland (most modern distros)
sudo apt install wl-clipboard

# X11
sudo apt install xclip
```

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/perryFile/phone-to-clipboard.git
cd phone-to-clipboard

# 2. Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Run
./run.sh
```

The server starts on port **8000**. A QR code is printed in the terminal — scan it with your phone.

Your phone and computer must be on the **same Wi-Fi network**.

---

## HTTPS (recommended for camera access)

Most phone browsers require HTTPS to access the camera. Set it up once with `mkcert`:

```bash
./scripts/setup-mkcert.sh
```

Then follow the printed instructions to install the root CA on your phone. After that, `./run.sh` automatically uses TLS.

---

## Usage

After starting the server:

| Action | How |
|--------|-----|
| **Scan QR** | Point your phone camera at the QR code in the terminal |
| **Send photo** | Tap the camera button, take a photo |
| **Send from library** | Tap "Choose from library", pick an image |
| **Send text** | Type in the text box, tap "Send text to clipboard" |
| **Paste** | Press Ctrl+V on your desktop |

The pairing page is also available at `http://<your-ip>:8000/pair` if QR scanning isn't working.

---

## Autostart on login (Linux)

```bash
# Install and enable the systemd user service
cp systemd/airdrop-linux.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now airdrop-linux
```

The server will start automatically when you log in.

---

## Running tests

```bash
PYTHONPATH= .venv/bin/pytest tests/ -q
```

---

## Security

- A random token is generated at first run and saved to `~/.config/airdrop_linux/token`.
- All upload endpoints require the token (via query param or header).
- A rate limiter blocks more than 3 requests per second per IP.
- The server only listens on your LAN IP — it is not exposed to the internet.

---

## Supported platforms

| Platform | Clipboard backend |
|----------|-------------------|
| Linux — Wayland | `wl-copy` |
| Linux — X11 | `xclip` |
| Windows | PowerShell `Set-Clipboard` |
