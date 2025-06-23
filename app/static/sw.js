const CACHE_NAME = "glimpser-offline-v1";
const MAX_SHOTS = 20;
const OFFLINE_URLS = [
  "/",
  "/status",
  "/discover",
  "/settings",
  "/templates",
  "/offline",
  "/static/css/style.css",
  "/static/css/player.css",
  "/static/js/script.js",
  "/static/js/discovery_scan.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_URLS)),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

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

function networkFirst(request) {
  return promiseTimeout(fetch(request), 5000)
    .then((response) => {
      caches
        .open(CACHE_NAME)
        .then((cache) => cache.put(request, response.clone()));
      return response;
    })
    .catch(() => caches.match(request));
}

function cacheLatestShots(request) {
  return promiseTimeout(fetch(request), 3000)
    .then((response) => {
      if (response.status === 504) throw new Error("Gateway timeout");
      const clone = response.clone();
      caches.open(CACHE_NAME).then(async (cache) => {
        await cache.put(request, clone);
        const keys = (await cache.keys()).filter(
          (k) => k.url.includes("/last_screenshot") || /\.jpe?g$/i.test(k.url),
        );
        while (keys.length > MAX_SHOTS) {
          await cache.delete(keys.shift());
        }
      });
      return response;
    })
    .catch(() => caches.match(request));
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
