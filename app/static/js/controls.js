export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const details = document.getElementById("controls-wrapper");
    if (!details) return;

    let hideTimeout;
    const scheduleHide = () => {
      clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => {
        details.classList.add("fade-out");
        setTimeout(() => {
          details.removeAttribute("open");
          details.classList.remove("fade-out");
        }, 500);
      }, 5000);
    };

    const showControls = () => {
      if (!details.open) return;
      details.classList.remove("fade-out");
      scheduleHide();
    };

    details.addEventListener("toggle", showControls);

    if (details.open) showControls();

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showControls);
    });
  });
}
