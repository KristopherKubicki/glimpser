const CACHE_NAME = "glimpser-offline-v6";
const MAX_SHOTS = 20;
const KIOSK_CACHE = "glimpser-kiosk-shell-v1";
const OFFLINE_URLS = [
  "/",
  "/status",
  "/discover",
  "/settings",
  "/offline",
  "/static/css/style.css",
  "/static/css/player.css",
  "/static/js/script.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // One unavailable optional page must not prevent offline kiosk startup.
      await Promise.allSettled(
        OFFLINE_URLS.map(async (url) => {
          const response = await completeFetch(url, 10000);
          if (response.ok) await cache.put(url, response);
        }),
      );
      await self.skipWaiting();
    }),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names.map((name) => {
            if (name.startsWith("glimpser-offline-") && name !== CACHE_NAME) {
              return caches.delete(name);
            }
            return Promise.resolve(false);
          }),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (isKioskPage(url)) {
    event.respondWith(networkFirst(request, KIOSK_CACHE));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Always use live network responses for dynamic API calls.
  // Returning stale cached JSON here can freeze group/live camera lists.
  if (url.pathname === "/templates" || url.pathname === "/groups") {
    event.respondWith(fetch(request));
    return;
  }

  // Never serve cached /live pages. They are stateful and should always use
  // the latest backend/runtime code after restarts.
  if (url.pathname.startsWith("/live")) {
    event.respondWith(fetch(request).catch(() => caches.match("/offline")));
    return;
  }

  if (OFFLINE_URLS.includes(url.pathname)) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request).then((res) => res || caches.match("/offline")),
    );
    return;
  }

  if (
    /\.jpe?g$/i.test(url.pathname) ||
    url.pathname.startsWith("/last_screenshot") ||
    url.pathname.endsWith("/stream.png")
  ) {
    event.respondWith(cacheLatestShots(request));
    return;
  }
});

self.addEventListener("push", (event) => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title, { body: data.body }),
  );
});

function isKioskPage(url) {
  return (
    url.origin === self.location.origin &&
    url.pathname === "/" &&
    ["office", "living"].includes(url.searchParams.get("profile"))
  );
}

self.addEventListener("message", (event) => {
  if (event.data?.type !== "CACHE_KIOSK_SHELL") return;
  const urls = event.data.urls;
  if (!Array.isArray(urls) || urls.length > 256) return;
  event.waitUntil(
    (async () => {
      try {
        await Promise.all(
          urls.map(async (value) => {
            const url = new URL(value, self.location.origin);
            if (
              url.origin !== self.location.origin ||
              (!isKioskPage(url) && !url.pathname.startsWith("/static/"))
            )
              throw new Error("Invalid kiosk cache URL");
            const response = await completeFetch(url.href, 10000, {
              cache: "reload",
            });
            if (!response.ok) throw new Error("Kiosk asset unavailable");
            const cache = await caches.open(
              isKioskPage(url) ? KIOSK_CACHE : CACHE_NAME,
            );
            await cache.put(url.href, response);
          }),
        );
        event.ports?.[0]?.postMessage({ ready: true });
      } catch {
        event.ports?.[0]?.postMessage({ ready: false });
      }
    })(),
  );
});

async function cachedResponse(request, cacheName) {
  try {
    return await (await caches.open(cacheName)).match(request);
  } catch {
    // Storage can be disabled or evicted independently of the network.
    return undefined;
  }
}

async function saveResponse(request, response, cacheName, shotsOnly = false) {
  try {
    const cache = await caches.open(cacheName);
    await cache.put(request, response.clone());
    let keys = await cache.keys();
    if (shotsOnly)
      keys = keys.filter((key) => {
        const path = new URL(key.url).pathname;
        return (
          path.startsWith("/last_screenshot") ||
          /\.jpe?g$/i.test(path) ||
          path.endsWith("/stream.png")
        );
      });
    const limit = shotsOnly ? MAX_SHOTS : cacheName === KIOSK_CACHE ? 8 : 320;
    for (const key of keys.slice(0, Math.max(0, keys.length - limit)))
      await cache.delete(key);
  } catch {
    // A quota or cache failure must never discard a healthy network response.
  }
}

async function networkFirst(request, cacheName = CACHE_NAME) {
  let response;
  try {
    response = await completeFetch(request, 5000);
  } catch {
    return cachedResponse(request, cacheName);
  }
  if (response.ok) await saveResponse(request, response, cacheName);
  else if (response.status >= 500)
    return (await cachedResponse(request, cacheName)) || response;
  return response;
}

async function cacheLatestShots(request) {
  let response;
  try {
    response = await completeFetch(request, 3000);
  } catch {
    return cachedResponse(request, CACHE_NAME);
  }
  // Server errors must not replace the last usable camera frame. Authentication
  // failures still reach the page unchanged instead of displaying saved footage.
  if (response.status >= 500)
    return (await cachedResponse(request, CACHE_NAME)) || response;
  if (response.ok) await saveResponse(request, response, CACHE_NAME, true);
  return response;
}

async function completeFetch(request, ms, options = {}) {
  const controller = new AbortController();
  try {
    return await promiseTimeout(
      (async () => {
        const response = await fetch(request, {
          ...options,
          signal: controller.signal,
        });
        // fetch resolves at headers. A broken link can then stall forever in
        // cache.put, preventing the saved page/frame from being used. Keep the
        // deadline through the body; the original response remains consumable.
        if (response.ok) await response.clone().arrayBuffer();
        return response;
      })(),
      ms,
    );
  } catch (error) {
    controller.abort();
    throw error;
  }
}

function promiseTimeout(promise, ms) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error("timeout")), ms);
  });
  return Promise.race([
    promise.finally(() => clearTimeout(timeoutId)),
    timeout,
  ]);
}
