export function initIndexTime() {
  document.addEventListener("DOMContentLoaded", () => {
    const elem = document.getElementById("index-time");
    if (!elem) return;
    const update = () => {
      const now = new Date();
      elem.textContent = now.toLocaleTimeString();
      elem.title = now.toISOString();
    };
    update();
    setInterval(update, 1000);
  });
}
