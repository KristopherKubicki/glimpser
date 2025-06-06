export function initFooterFade() {
  document.addEventListener("DOMContentLoaded", () => {
    const footer = document.querySelector("footer");
    const main = document.querySelector("main");
    if (!footer || !main) return;

    const updatePadding = () => {
      document.documentElement.style.setProperty(
        "--footer-space",
        `${footer.offsetHeight}px`,
      );
    };

    updatePadding();
    window.addEventListener("resize", updatePadding);

    let fadeTimeout;

    const showFooter = () => {
      footer.classList.remove("fade-out");
      clearTimeout(fadeTimeout);
      fadeTimeout = setTimeout(() => footer.classList.add("fade-out"), 3000);
    };

    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showFooter);
    });

    showFooter();
  });
}
