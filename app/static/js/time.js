export function initIndexTime() {
  const setup = () => {
    const elem = document.getElementById("index-time");
    if (!elem) return;
    const update = () => {
      const now = new Date();
      elem.textContent = now.toLocaleTimeString();
      elem.title = now.toISOString();
    };
    update();
    setInterval(update, 1000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
}
