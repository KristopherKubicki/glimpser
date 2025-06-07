export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const details = document.getElementById("controls-wrapper");
    if (!details) return;

    let hideTimeout;
    const scheduleHide = () => {
      clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => details.removeAttribute("open"), 5000);
    };

    details.addEventListener("toggle", () => {
      if (details.open) scheduleHide();
    });

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, () => {
        if (details.open) scheduleHide();
      });
    });
  });
}
