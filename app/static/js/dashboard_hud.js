// Dashboard screenshots already contain their own charts, labels, and summaries.
export function simplifyDashboardHud(root = document) {
  root.querySelectorAll(".landing-scene[data-hero-name]").forEach((scene) => {
    if (
      !/^(Hubitat|Phobos)|Dashboard|SystemGlimpse|^Bandwidth(?:TX|RX)$/.test(
        scene.dataset.heroName,
      )
    )
      return;
    const strip = scene.querySelector(".kiosk-caption-strip");
    if (!strip || scene.classList.contains("is-dashboard-view")) return;
    scene.classList.add("is-dashboard-view");
    for (const selector of [
      ".landing-hero-bug",
      ".landing-capture-age",
      ".kiosk-source-age",
    ]) {
      const node = scene.querySelector(selector);
      if (node) strip.append(node);
    }
  });
}
