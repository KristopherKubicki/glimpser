export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const wrapper = document.getElementById("controls-wrapper");
    if (!wrapper) return;

    const isMobile = window.matchMedia("(max-width: 767px)").matches;
    if (isMobile) {
      return;
    }

    let fadeTimeout;
    const showControls = () => {
      wrapper.classList.remove("fade-out");
      clearTimeout(fadeTimeout);
      fadeTimeout = setTimeout(() => wrapper.classList.add("fade-out"), 3000);
    };

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showControls);
    });
    wrapper.addEventListener("mouseover", showControls);

    showControls();
  });
}
