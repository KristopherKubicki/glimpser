export function initControlsDropdown() {
  document.addEventListener("DOMContentLoaded", () => {
    const wrapper = document.getElementById("controls-wrapper");
    const toggle = document.getElementById("controls-toggle");
    if (!wrapper || !toggle) return;

    let hideTimeout;
    let buttonTimeout;

    const showButton = () => {
      wrapper.classList.add("show-toggle");
      clearTimeout(buttonTimeout);
      if (wrapper.classList.contains("closed")) {
        buttonTimeout = setTimeout(
          () => wrapper.classList.remove("show-toggle"),
          3000,
        );
      }
    };

    const scheduleHide = () => {
      clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => {
        wrapper.classList.add("fade-out");
        setTimeout(() => {
          wrapper.classList.add("closed");
          wrapper.classList.remove("fade-out");
          showButton();
        }, 500);
      }, 5000);
    };

    const showControls = () => {
      if (wrapper.classList.contains("closed")) return;
      wrapper.classList.remove("fade-out");
      showButton();
      scheduleHide();
    };

    toggle.addEventListener("click", () => {
      wrapper.classList.toggle("closed");
      if (!wrapper.classList.contains("closed")) showControls();
      else showButton();
    });

    if (!wrapper.classList.contains("closed")) showControls();
    else showButton();

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showButton);
    });
  });
}
