import { sendTelemetry } from "./telemetry.js";

export function initUrlTester() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("url");
    const status = document.getElementById("url-status");
    const preview = document.getElementById("url-preview");
    if (!input || !status) return;

    const form = input.closest("form");
    const controlled = [];
    if (form) {
      form.querySelectorAll("input, select, textarea").forEach((el) => {
        if (el === input || el.id === "name") return;
        controlled.push([el, el.disabled]);
      });
    }

    const toggleDisabled = () => {
      const disable = input.value.trim() === "";
      controlled.forEach(([el, orig]) => {
        el.disabled = disable || orig;
      });
    };

    let controller;
    const defaultSrc = preview
      ? preview.dataset.placeholder || preview.src
      : "";
    const setStatus = (cls) => {
      status.textContent = "";
      status.className = "url-status" + (cls ? ` ${cls}` : "");
    };

    const check = async () => {
      const url = input.value.trim();
      setStatus("");
      if (preview) preview.src = url || defaultSrc;
      if (!url) return;
      controller?.abort();
      controller = new AbortController();
      setStatus("pending");
      try {
        const res = await fetch(
          `/templates/test_url?url=${encodeURIComponent(url)}`,
          {
            signal: controller.signal,
          },
        );
        const data = await res.json();
        if (res.ok && data.ok) {
          setStatus("ok");
        } else {
          setStatus("bad");
        }
        sendTelemetry("url_test", { url, ok: data.ok });
      } catch {
        if (controller.signal.aborted) return;
        setStatus("bad");
        sendTelemetry("url_test", { url, ok: false });
      }
    };

    toggleDisabled();
    input.addEventListener("input", () => {
      toggleDisabled();
      setStatus(input.value.trim() ? "pending" : "");
    });
    input.addEventListener("blur", check);
    input.addEventListener("change", () => {
      check();
    });
  });
}
