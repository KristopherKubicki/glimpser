export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const details = document.getElementById("controls-wrapper");
    if (!details) return;

    let hideTimeout;
    let buttonTimeout;

    const showButton = () => {
      details.classList.add("show-summary");
      clearTimeout(buttonTimeout);
      if (!details.open) {
        buttonTimeout = setTimeout(
          () => details.classList.remove("show-summary"),
          3000,
        );
      }
    };

    const scheduleHide = () => {
      clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => {
        details.classList.add("fade-out");
        setTimeout(() => {
          details.removeAttribute("open");
          details.classList.remove("fade-out");
          showButton();
        }, 500);
      }, 5000);
    };

    const showControls = () => {
      if (!details.open) return;
      details.classList.remove("fade-out");
      showButton();
      scheduleHide();
    };

    details.addEventListener("toggle", showControls);

    if (details.open) showControls();
    else showButton();

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showButton);
    });
  });
}
