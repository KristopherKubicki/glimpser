(() => {
  const root = document.querySelector(".sat[data-frames]");
  if (!root) return;
  const dates = JSON.parse(root.dataset.frames);
  if (!dates.length) return;
  const image = document.getElementById("sat-image");
  const label = document.getElementById("sat-date");
  const slider = document.getElementById("sat-slider");
  const play = document.getElementById("sat-play");
  let timer = null;
  let index = dates.length - 1;
  const cache = new Map();
  const src = (date) => `/satellite/media/${date}.jpg`;
  function preload(next) {
    if (next < 0 || next >= dates.length || cache.has(next)) return;
    const ahead = new Image();
    ahead.src = src(dates[next]);
    cache.set(next, ahead);
    if (cache.size > 8) cache.delete(cache.keys().next().value);
  }
  function show(next) {
    index = Math.max(0, Math.min(dates.length - 1, next));
    const date = dates[index];
    image.src = src(date);
    label.textContent = date;
    slider.value = String(index);
    slider.style.setProperty(
      "--sat-progress",
      `${dates.length === 1 ? 100 : (100 * index) / (dates.length - 1)}%`,
    );
    document.getElementById("sat-prev").disabled = index === 0;
    document.getElementById("sat-next").disabled = index === dates.length - 1;
    preload(index + 1);
    preload(index - 1);
  }
  function stop() {
    clearInterval(timer);
    timer = null;
    play.innerHTML = "▶ <span>Play</span>";
    play.setAttribute("aria-label", "Play timelapse");
  }
  document
    .getElementById("sat-prev")
    .addEventListener("click", () => show(index - 1));
  document
    .getElementById("sat-next")
    .addEventListener("click", () => show(index + 1));
  slider.addEventListener("input", () => show(Number(slider.value)));
  play.addEventListener("click", () => {
    if (timer) return stop();
    if (index === dates.length - 1) show(0);
    play.innerHTML = "Ⅱ <span>Pause</span>";
    play.setAttribute("aria-label", "Pause timelapse");
    timer = setInterval(() => show((index + 1) % dates.length), 850);
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === "ArrowLeft") show(index - 1);
    if (event.key === "ArrowRight") show(index + 1);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && timer) stop();
  });
  show(index);
})();
