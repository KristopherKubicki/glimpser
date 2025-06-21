export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const wrapper = document.getElementById("controls-wrapper");
    if (!wrapper) return;

    let fadeTimeout;
    const showControls = () => {
      wrapper.classList.remove("fade-out");
      clearTimeout(fadeTimeout);
      fadeTimeout = setTimeout(() => wrapper.classList.add("fade-out"), 3000);
    };

    const pauseFade = () => {
      wrapper.classList.remove("fade-out");
      clearTimeout(fadeTimeout);
    };

    ["mousemove", "scroll", "touchstart"].forEach((evt) => {
      document.addEventListener(evt, showControls);
    });
    wrapper.addEventListener("mouseenter", pauseFade);
    wrapper.addEventListener("mouseleave", showControls);

    showControls();
  });
}
