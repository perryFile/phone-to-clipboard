/**
 * Service Worker — caches the app shell so it loads instantly.
 *
 * Strategy: Cache-First for shell assets, Network-Only for API endpoints.
 * The token lives in the URL query string so the cached page still works with
 * the current token after an OS swap.
 */

const CACHE_NAME = "airdrop-linux-v2";

// Assets that make up the app shell
const SHELL_ASSETS = [
  "/",
  "/app.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// ---------------------------------------------------------------------------
// Install — pre-cache shell assets
// ---------------------------------------------------------------------------
self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then(function (cache) {
        // Cache each asset individually so one failure doesn't break the install
        return Promise.allSettled(
          SHELL_ASSETS.map(function (url) {
            return cache.add(url).catch(function (err) {
              console.warn("[SW] Failed to cache", url, err);
            });
          })
        );
      })
      .then(function () {
        return self.skipWaiting();
      })
  );
});

// ---------------------------------------------------------------------------
// Activate — clean up old caches
// ---------------------------------------------------------------------------
self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (k) { return k !== CACHE_NAME; })
            .map(function (k) { return caches.delete(k); })
        );
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

// ---------------------------------------------------------------------------
// Fetch — network-only for API, cache-first for shell
// ---------------------------------------------------------------------------
self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);

  // Never intercept cross-origin requests
  if (url.origin !== self.location.origin) return;

  // Network-only for API endpoints
  if (url.pathname === "/upload" || url.pathname === "/upload-text" || url.pathname === "/health" || url.pathname === "/client-log") return;

  // Cache-first for everything else (shell assets)
  event.respondWith(
    caches.match(event.request).then(function (cached) {
      if (cached) return cached;
      return fetch(event.request).then(function (response) {
        // Cache successful GET responses for shell paths
        if (
          event.request.method === "GET" &&
          response.status === 200
        ) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(event.request, clone);
          });
        }
        return response;
      });
    })
  );
});
