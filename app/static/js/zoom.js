export function initVideoZoom() {
  /**
   * Apply wheel-based zoom to an element.
   * @param {HTMLElement} el - Target element.
   */
  function applyWheelZoom(el) {
    let scale = 1;
    let resetId;
    const applyScale = (x, y) => {
      el.style.transformOrigin = `${x}% ${y}%`;
      el.style.transform = `scale(${scale})`;
    };
    el.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        if (resetId) {
          clearTimeout(resetId);
          resetId = null;
        }
        const rect = el.getBoundingClientRect();
        const originX = ((e.clientX - rect.left) / rect.width) * 100;
        const originY = ((e.clientY - rect.top) / rect.height) * 100;
        scale += e.deltaY < 0 ? 0.1 : -0.1;
        scale = Math.min(3, Math.max(1, scale));
        applyScale(originX, originY);
      },
      { passive: false },
    );
    el.addEventListener("mouseleave", () => {
      if (resetId) clearTimeout(resetId);
      resetId = setTimeout(() => {
        scale = 1;
        el.style.transform = "";
        el.style.transformOrigin = "";
      }, 1000);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const video = document.getElementById("live-video");
    if (video) applyWheelZoom(video);

    const previews = document.querySelectorAll(".edit-template-preview img");
    previews.forEach((img) => applyWheelZoom(img));
  });
}
