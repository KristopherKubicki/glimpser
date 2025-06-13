export function computeProgress(now, next, frequencyMinutes) {
  const total = frequencyMinutes * 60000;
  if (!total) return 0;
  const diff = new Date(next).getTime() - now;
  const progress = 1 - diff / total;
  return Math.max(0, Math.min(1, progress));
}

export function initCaptureCountdown() {
  const update = () => {
    document.querySelectorAll(".capture-dot[data-next]").forEach((dot) => {
      const next = dot.getAttribute("data-next");
      const freq = parseFloat(dot.getAttribute("data-frequency")) || 0;
      if (!next || !freq) return;
      if (dot.classList.contains("active")) {
        dot.style.removeProperty("--capture-angle");
        dot.title = "Capturing...";
        return;
      }
      const progress = computeProgress(Date.now(), next, freq);
      const angle = progress * 360;
      dot.style.setProperty("--capture-angle", `${angle}deg`);
      const diff = new Date(next).getTime() - Date.now();
      const secs = Math.max(0, Math.ceil(diff / 1000));
      dot.title = `Next in ${secs}s`;
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      update();
      setInterval(update, 1000);
    });
  } else {
    update();
    setInterval(update, 1000);
  }
}
