import { sendTelemetry } from "./telemetry.js";

export function initUrlTester() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("url");
    const status = document.getElementById("url-status");
    const preview = document.getElementById("url-preview");
    if (!input || !status) return;

    let controller;
    const check = async () => {
      const url = input.value.trim();
      status.textContent = "";
      status.className = "url-status";
      if (preview) preview.src = url;
      if (!url) return;
      controller?.abort();
      controller = new AbortController();
      status.textContent = "…";
      try {
        const res = await fetch(
          `/templates/test_url?url=${encodeURIComponent(url)}`,
          {
            signal: controller.signal,
          },
        );
        const data = await res.json();
        if (res.ok && data.ok) {
          status.textContent = "✓";
          status.classList.add("ok");
        } else {
          status.textContent = "✗";
          status.classList.add("bad");
        }
        sendTelemetry("url_test", { url, ok: data.ok });
      } catch {
        if (controller.signal.aborted) return;
        status.textContent = "✗";
        status.classList.add("bad");
        sendTelemetry("url_test", { url, ok: false });
      }
    };

    input.addEventListener("blur", check);
    input.addEventListener("change", () => {
      check();
    });
  });
}
