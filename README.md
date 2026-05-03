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

> Windows support is currently **in progress**. Core flows work for many setups, but edge cases are still being polished.

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

The server starts on port **8765** by default. A QR code is printed in the terminal — scan it with your phone.

---

## Start from anywhere (no `cd` needed)

This is optional and does **not** enable autostart.

After the first install, register the CLI command once:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Then you can launch from any folder (while your venv is active):

```bash
phone-to-clipboard
```

If you want this to work even without manually activating the venv each time:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/.venv/bin/phone-to-clipboard" ~/.local/bin/phone-to-clipboard
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Now `phone-to-clipboard` works from anywhere and still only runs when you start it.

Your phone and computer must be on the **same Wi-Fi network**.

---

## Windows tutorial (download + run)

Follow this on a Windows PC.

> Status: **in progress**. If something fails, open an issue with the exact error so we can improve Windows compatibility quickly.

1. Install Git: https://git-scm.com/download/win
2. Install Python 3.11+ (check **Add Python to PATH**): https://www.python.org/downloads/windows/
3. Open PowerShell and run:

```powershell
git clone https://github.com/perryFile/phone-to-clipboard.git
cd phone-to-clipboard
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
phone-to-clipboard
```

If PowerShell blocks activation, run once as admin:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then retry:

```powershell
.\.venv\Scripts\Activate.ps1
```

Optional: run from any folder without activating the venv every time:

```powershell
setx PATH "$env:PATH;$PWD\.venv\Scripts"
```

Close and reopen PowerShell after `setx`, then run:

```powershell
phone-to-clipboard
```

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

The pairing page is also available at `http://<your-ip>:8765/pair` if QR scanning isn't working.

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
| Windows (in progress) | PowerShell `Set-Clipboard` |

---

## Changelog

### 2026-05-03

- Fixed iPhone "Take photo" reliability by switching to an explicit camera button click flow.
- Added a Linux clipboard compatibility fallback that converts JPEG uploads to PNG before copy on Wayland/X11.
- Bumped service worker cache version so phones pick up frontend fixes immediately.
- Added an optional global `phone-to-clipboard` command so the app can be started from any folder.
- Improved Windows clipboard reliability by running PowerShell in STA mode for image/text clipboard operations.
- Added a full Windows download/setup/run tutorial.
