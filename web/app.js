/**
 * airdrop-linux — iPhone camera → Linux clipboard
 */

(function () {
  "use strict";

  // ----- Helpers -----

  /** Read the auth token from the current URL query string (?t=...) */
  function getToken() {
    return new URLSearchParams(window.location.search).get("t") || "";
  }

  const token = getToken();

  // Warn in console if no token; upload will 401 but let the server say so.
  if (!token) {
    console.warn("No ?t= token in URL. Uploads will be rejected.");
  }

  // ----- DOM refs -----
  const input       = /** @type {HTMLInputElement} */ (document.getElementById("photo-input"));
  const uploadInput = /** @type {HTMLInputElement} */ (document.getElementById("upload-input"));
  const label       = document.getElementById("camera-label");
  const uploadLabel = document.getElementById("upload-label");
  const textInput   = /** @type {HTMLTextAreaElement} */ (document.getElementById("text-input"));
  const textSendBtn = /** @type {HTMLButtonElement} */ (document.getElementById("text-send-btn"));
  const status      = document.getElementById("status");
  const a2hsBanner  = document.getElementById("a2hs-banner");

  // ----- Status helpers -----

  function setStatus(cls, html) {
    status.className = cls;
    status.innerHTML = html;
  }

  function setIdle(msg) {
    setStatus("idle", msg || "Tap the button to take a photo.");
  }

  function setLoading(msg) {
    setStatus(
      "loading",
      '<span class="spinner" aria-hidden="true"></span>' + (msg || "Uploading…")
    );
  }

  function setOk(msg) {
    setStatus("ok", "✓ " + (msg || "Copied to clipboard"));
    // Reset to idle after 3 s
    setTimeout(setIdle, 3000);
  }

  function setError(msg) {
    setStatus("error", "✗ " + (msg || "Something went wrong"));
  }

  async function sendClientLog(eventType, detail) {
    if (!token) {
      return;
    }

    const payload = {
      event: eventType,
      detail: detail || "",
      userAgent: navigator.userAgent,
      ts: Date.now(),
    };

    try {
      await fetch("/client-log?t=" + encodeURIComponent(token), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Token": token,
        },
        body: JSON.stringify(payload),
        keepalive: true,
      });
    } catch (err) {
      console.warn("Failed to send client log:", err);
    }
  }

  // ----- Upload -----

  function setAllDisabled(disabled) {
    label.classList.toggle("disabled", disabled);
    if (uploadLabel) uploadLabel.classList.toggle("disabled", disabled);
    if (textSendBtn) textSendBtn.disabled = disabled;
  }

  async function uploadText(text) {
    setAllDisabled(true);
    setLoading("Sending text ...");
    await sendClientLog("text_upload_started", "chars=" + text.length);

    try {
      const resp = await fetch("/upload-text?t=" + encodeURIComponent(token), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Token": token,
        },
        body: JSON.stringify({ text: text }),
      });

      const json = await resp.json().catch(() => ({}));

      if (resp.ok) {
        setOk(json.message || "Text copied to clipboard — paste with Ctrl+V");
        await sendClientLog("text_upload_ok", "chars=" + text.length);
        if (textInput) textInput.value = "";
      } else if (resp.status === 401) {
        var pairUrl = window.location.origin + "/pair";
        setError("Auth failed. <a href='" + pairUrl + "' style='color:inherit;text-decoration:underline'>Open the pairing page</a> to get the correct link.");
        await sendClientLog("text_upload_failed", "401 auth failed");
      } else if (resp.status === 413) {
        setError("Text too large (max 256 KB).");
        await sendClientLog("text_upload_failed", "413 text too large");
      } else if (resp.status === 422) {
        setError("Please enter some text first.");
        await sendClientLog("text_upload_failed", "422 empty text");
      } else if (resp.status === 429) {
        setError("Too many requests — please wait a moment.");
        await sendClientLog("text_upload_failed", "429 rate limited");
      } else if (resp.status === 503) {
        setError("Clipboard error on computer: " + (json.detail || "check server logs"));
        await sendClientLog("text_upload_failed", "503 clipboard error: " + (json.detail || "unknown"));
      } else {
        setError("Server error " + resp.status + ": " + (json.detail || ""));
        await sendClientLog("text_upload_failed", "HTTP " + resp.status + ": " + (json.detail || ""));
      }
    } catch (err) {
      setError(
        "Cannot reach your computer. " +
        "Connect phone + computer to the same Wi-Fi (not 5G), " +
        "or use Tailscale for cross-network access. " +
        (err && err.message ? "(" + err.message + ")" : "")
      );
      await sendClientLog("text_upload_failed", "network error: " + err.message);
    } finally {
      setAllDisabled(false);
    }
  }

  async function uploadPhoto(file, source) {
    setAllDisabled(true);
    setLoading("Uploading " + file.name + " ...");
    await sendClientLog(
      "upload_started",
      "source=" + (source || "camera") + ",name=" + file.name + ",size=" + file.size + ",type=" + (file.type || "unknown")
    );

    const form = new FormData();
    form.append("photo", file);

    try {
      const resp = await fetch("/upload?t=" + encodeURIComponent(token), {
        method: "POST",
        headers: {
          "X-Token": token,
        },
        body: form,
      });

      const json = await resp.json().catch(() => ({}));

      if (resp.ok) {
        setOk(json.message || "Copied to clipboard — paste with Ctrl+V");
        await sendClientLog("upload_ok", json.message || "Image copied to clipboard");
      } else if (resp.status === 401) {
        var pairUrl = window.location.origin + "/pair";
        setError("Auth failed. <a href='" + pairUrl + "' style='color:inherit;text-decoration:underline'>Open the pairing page</a> to get the correct link.");
        await sendClientLog("upload_failed", "401 auth failed");
      } else if (resp.status === 413) {
        setError("Photo is too large (max 25 MB).");
        await sendClientLog("upload_failed", "413 photo too large");
      } else if (resp.status === 422) {
        setError("Could not process image: " + (json.detail || "unknown error"));
        await sendClientLog("upload_failed", "422 image error: " + (json.detail || "unknown"));
      } else if (resp.status === 429) {
        setError("Too many requests — please wait a moment.");
        await sendClientLog("upload_failed", "429 rate limited");
      } else if (resp.status === 503) {
        setError("Clipboard error on Linux: " + (json.detail || "check server logs"));
        await sendClientLog("upload_failed", "503 clipboard error: " + (json.detail || "unknown"));
      } else {
        setError("Server error " + resp.status + ": " + (json.detail || ""));
        await sendClientLog("upload_failed", "HTTP " + resp.status + ": " + (json.detail || ""));
      }
    } catch (err) {
      setError(
        "Cannot reach your computer. " +
        "Connect phone + computer to the same Wi-Fi (not 5G), " +
        "or use Tailscale for cross-network access. " +
        (err && err.message ? "(" + err.message + ")" : "")
      );
      await sendClientLog("upload_failed", "network error: " + err.message);
    } finally {
      setAllDisabled(false);
      // Reset both inputs so the same file can be re-sent if needed
      input.value = "";
      if (uploadInput) uploadInput.value = "";
    }
  }

  // ----- Event wiring -----

  input.addEventListener("change", function () {
    const file = input.files && input.files[0];
    if (!file) {
      sendClientLog("photo_not_selected", "camera opened but no file selected");
      return;
    }
    sendClientLog(
      "photo_selected",
      "source=camera,name=" + file.name + ",size=" + file.size + ",type=" + (file.type || "unknown")
    );
    uploadPhoto(file, "camera");
  });

  if (uploadInput) {
    uploadInput.addEventListener("change", function () {
      const file = uploadInput.files && uploadInput.files[0];
      if (!file) return;
      sendClientLog(
        "photo_selected",
        "source=library,name=" + file.name + ",size=" + file.size + ",type=" + (file.type || "unknown")
      );
      uploadPhoto(file, "library");
    });
  }

  if (label) {
    label.addEventListener("click", function () {
      sendClientLog("camera_opened", "camera button tapped");
      // Reset so selecting/capturing again always triggers a change event.
      input.value = "";
      input.click();
    });
  }

  if (uploadLabel) {
    uploadLabel.addEventListener("click", function () {
      sendClientLog("library_opened", "upload from library tapped");
    });
  }

  if (textSendBtn && textInput) {
    textSendBtn.addEventListener("click", function () {
      var text = textInput.value || "";
      if (!text.trim()) {
        setError("Please enter some text first.");
        return;
      }
      uploadText(text);
    });
  }

  // ----- Add-to-Home-Screen hint -----
  // navigator.standalone is true when already running as a PWA
  const isStandalone =
    window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches;

  if (!isStandalone && /iPhone|iPod/.test(navigator.userAgent)) {
    // Show hint after 4 s to avoid distraction on first visit
    setTimeout(function () {
      if (a2hsBanner) a2hsBanner.style.display = "block";
    }, 4000);
  }

  // ----- Service worker registration -----
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker
        .register("/sw.js")
        .catch(function (err) {
          console.warn("Service worker registration failed:", err);
        });
    });
  }
})();
