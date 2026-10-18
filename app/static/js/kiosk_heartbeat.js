// The external kiosk monitor checks these beats, not just server reachability.
export function mountKioskHeartbeat(profile) {
  if (
    !["office", "living"].includes(profile) ||
    typeof requestAnimationFrame !== "function"
  )
    return () => {};
  let disposed = false,
    pending = false,
    frame = null;
  const beat = () => {
    if (disposed || pending || document.hidden) return;
    pending = true;
    frame = requestAnimationFrame(() => {
      frame = null;
      if (disposed) return;
      const controller =
        typeof AbortController === "function" ? new AbortController() : null;
      const timeout = setTimeout(() => controller?.abort(), 5000);
      void fetch(`/kiosk_health?profile=${profile}`, {
        method: "POST",
        cache: "no-store",
        signal: controller?.signal,
      })
        .catch(() => {})
        .finally(() => {
          clearTimeout(timeout);
          pending = false;
        });
    });
  };
  beat();
  const timer = setInterval(beat, 15000);
  const dispose = () => {
    disposed = true;
    clearInterval(timer);
    if (frame !== null) cancelAnimationFrame(frame);
  };
  window.addEventListener("pagehide", dispose, { once: true });
  return dispose;
}
