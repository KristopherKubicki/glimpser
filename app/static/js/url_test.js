import { sendTelemetry } from "./telemetry.js";

export function initUrlTester() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("url");
    const status = document.getElementById("url-status");
    const preview = document.getElementById("url-preview");
    if (!input || !status) return;

    const form = input.closest("form");
    const controlled = [];
    let submit;
    if (form) {
      form.querySelectorAll("input, select, textarea").forEach((el) => {
        if (el === input || el.id === "name") return;
        if (!submit && el.type === "submit") submit = el;
        controlled.push([el, el.disabled]);
      });
    }

    const toggleDisabled = () => {
      const disable = input.value.trim() === "";
      controlled.forEach(([el, orig]) => {
        el.disabled = disable || orig;
      });
      if (submit) submit.disabled = disable;
    };

    let controller;
    const defaultSrc = preview
      ? preview.dataset.placeholder || preview.src
      : "";
    const defaultUrl = input.dataset.defaultUrl;
    const setStatus = (cls) => {
      status.textContent = "";
      status.className = "url-status" + (cls ? ` ${cls}` : "");
    };

    const check = async () => {
      const url = input.value.trim();
      setStatus("");
      if (preview) preview.src = url || defaultSrc;
      if (submit) submit.disabled = true;
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
          if (submit) submit.disabled = false;
        } else {
          setStatus("bad");
          if (submit) submit.disabled = true;
        }
        sendTelemetry("url_test", { url, ok: data.ok });
      } catch {
        if (controller.signal.aborted) return;
        setStatus("bad");
        if (submit) submit.disabled = true;
        sendTelemetry("url_test", { url, ok: false });
      }
    };

    toggleDisabled();
    if (!input.value && defaultUrl) {
      input.value = defaultUrl;
      toggleDisabled();
      setTimeout(() => {
        check();
      }, 1000);
    }
    input.addEventListener("input", () => {
      toggleDisabled();
      setStatus(input.value.trim() ? "pending" : "");
      if (submit) submit.disabled = true;
    });
    input.addEventListener("paste", () => {
      setTimeout(() => {
        check();
      }, 0);
    });
    input.addEventListener("blur", check);
    input.addEventListener("change", () => {
      check();
    });
  });
}
