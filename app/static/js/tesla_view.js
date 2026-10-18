export function ageLabel(row, now) {
  const at = row?.captured_at;
  if (!Number.isFinite(at) || at > now + 5) return "Image age unknown";
  const minutes = Math.max(0, Math.floor((now - at) / 60));
  const age =
    minutes < 1
      ? "just now"
      : minutes < 60
        ? `${minutes}m ago`
        : `${Math.floor(minutes / 60)}h ago`;
  return `${row.state === "fresh" ? "Captured" : "Older image"} · ${age}`;
}

// Load the exact publication before changing either the visible image or its age.
export function savedImageUpdater(card) {
  const image = card.querySelector("img");
  const label = card.querySelector("[data-age]");
  let shown = null,
    pending = null,
    timeout;
  const cancel = () => {
    clearTimeout(timeout);
    if (pending) pending.onload = pending.onerror = null;
    pending = null;
  };
  const update = (row, now) => {
    if (!Number.isFinite(row?.captured_at) || row.captured_at > now + 5) {
      cancel();
      card.dataset.health = "unknown";
      label.textContent = "Saved image · age unverified";
      return;
    }
    if (shown?.captured_at === row.captured_at) {
      card.dataset.health = row.state;
      label.textContent = ageLabel(row, now);
      return;
    }
    cancel();
    label.textContent = shown ? ageLabel(shown, now) : "Loading saved image…";
    const next = new Image();
    pending = next;
    const failed = () => {
      cancel();
      card.dataset.health = "unknown";
      label.textContent = shown
        ? `${ageLabel(shown, Date.now() / 1000)} · refresh failed`
        : "Saved image · age unverified";
    };
    next.onerror = failed;
    next.onload = () => {
      if (!next.naturalWidth) return failed();
      image.src = next.src;
      shown = row;
      card.dataset.health = row.state;
      label.textContent = ageLabel(row, Date.now() / 1000);
      cancel();
    };
    timeout = setTimeout(failed, 10000);
    const stamp = new Date(row.captured_at * 1000).toISOString();
    next.src = `/last_screenshot/${encodeURIComponent(card.dataset.feed)}?capture=${encodeURIComponent(stamp)}`;
  };
  return { update, cancel };
}

export function mountTeslaView(root = document) {
  const cards = [...root.querySelectorAll("[data-feed]")];
  if (!cards.length) return () => {};
  let pending = false,
    disposed = false,
    controller;
  const images = new Map(cards.map((card) => [card, savedImageUpdater(card)]));
  const status = root.querySelector("#tesla-status");
  const details = root.querySelector("#tesla-details");
  const failed = () => {
    status.textContent = "Capture status unavailable";
    details.textContent = "Waiting for fresh collector health.";
    for (const card of cards) {
      images.get(card).cancel();
      card.dataset.health = "unknown";
      card.querySelector("[data-age]").textContent =
        "Saved image · age unverified";
    }
  };
  const poll = async () => {
    if (pending || disposed || document.hidden) return;
    pending = true;
    controller =
      typeof AbortController === "function" ? new AbortController() : null;
    const timeout = setTimeout(() => controller?.abort(), 5000);
    try {
      const response = await fetch("/tesla/status", {
        cache: "no-store",
        signal: controller?.signal,
      });
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (disposed) return;
      const now = Date.now() / 1000;
      if (
        !Number.isFinite(data.checked_at) ||
        now - data.checked_at > 300 ||
        data.checked_at > now + 5 ||
        !Array.isArray(data.feeds)
      )
        throw new Error("Stale collector");
      const live = data.workers?.live || {};
      const app = data.workers?.app || {};
      status.textContent =
        live.schedule === "active"
          ? live.state === "failed"
            ? `${data.fresh_cameras}/4 recent views · refresh failed`
            : `${data.fresh_cameras}/4 recent exterior views`
          : live.schedule === "inactive"
            ? "Exterior capture paused"
            : "Exterior schedule unavailable";
      const reason =
        {
          sentry_off: "Last attempt found Sentry Mode off.",
          budget: "Daily capture allowance reached.",
          capture_failed: "Last exterior capture failed.",
        }[live.reason] || "";
      details.textContent = `Cameras: ${live.schedule || "unknown"}. Map / overview: ${app.state === "failed" ? "refresh failed" : app.schedule || "unknown"}. ${reason}`;
      for (const card of cards) {
        const name = card.dataset.feed;
        const row = data.feeds.find((r) => r.name === name);
        images.get(card).update(row, now);
      }
    } catch {
      if (!disposed) failed();
    } finally {
      clearTimeout(timeout);
      pending = false;
    }
  };
  const visible = () => {
    if (!document.hidden) void poll();
  };
  const timer = setInterval(poll, 30000);
  const dispose = () => {
    disposed = true;
    controller?.abort();
    clearInterval(timer);
    for (const updater of images.values()) updater.cancel();
    window.removeEventListener("pagehide", dispose);
    document.removeEventListener("visibilitychange", visible);
  };
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("pagehide", dispose, { once: true });
  void poll();
  return dispose;
}
if (typeof document !== "undefined") mountTeslaView();
