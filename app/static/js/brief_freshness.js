import { captureAge, sourceAge, sourceNeedsAttention } from "./capture_age.js";
export function updateBriefAges(root = document) {
  root.querySelectorAll("[data-brief-captured]").forEach((node) => {
    node.textContent = `Captured ${captureAge(node.dataset.briefCaptured)}`;
  });
  root.querySelectorAll("[data-brief-freshness]").forEach((node) => {
    let freshness = {};
    try {
      freshness = JSON.parse(node.dataset.briefFreshness || "{}");
    } catch {
      /* Treat malformed metadata as unknown. */
    }
    node.textContent = sourceAge(freshness);
    node.classList.toggle("is-source-older", sourceNeedsAttention(freshness));
  });
}
if (document.querySelector("[data-brief-captured]")) {
  updateBriefAges();
  const timer = window.setInterval(updateBriefAges, 10000);
  window.addEventListener("pagehide", () => window.clearInterval(timer), {
    once: true,
  });
}
