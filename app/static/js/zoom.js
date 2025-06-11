export function initVideoZoom() {
  document.addEventListener("DOMContentLoaded", () => {
    const video = document.getElementById("live-video");
    if (!video) return;

    let scale = 1;
    let resetId;

    const applyScale = (x, y) => {
      video.style.transformOrigin = `${x}% ${y}%`;
      video.style.transform = `scale(${scale})`;
    };

    video.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        if (resetId) {
          clearTimeout(resetId);
          resetId = null;
        }
        const rect = video.getBoundingClientRect();
        const originX = ((e.clientX - rect.left) / rect.width) * 100;
        const originY = ((e.clientY - rect.top) / rect.height) * 100;
        scale += e.deltaY < 0 ? 0.1 : -0.1;
        scale = Math.min(3, Math.max(1, scale));
        applyScale(originX, originY);
      },
      { passive: false },
    );

    video.addEventListener("mouseleave", () => {
      if (resetId) clearTimeout(resetId);
      resetId = setTimeout(() => {
        scale = 1;
        video.style.transform = "";
        video.style.transformOrigin = "";
      }, 1000);
    });
  });
}
