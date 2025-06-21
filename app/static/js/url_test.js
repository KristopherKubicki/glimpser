import { sendTelemetry } from "./telemetry.js";

export function initUrlTester() {
  document.addEventListener("DOMContentLoaded", () => {
    const inputs = document.querySelectorAll("#url");
    if (!inputs.length) return;

    inputs.forEach((input) => {
      const container = input.closest(".edit-template-container");
      const status = container
        ? container.querySelector("#url-status")
        : document.getElementById("url-status");
      const preview = container
        ? container.querySelector("img")
        : document.getElementById("url-preview");
      if (!status) return;

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
      const debounce = (fn, delay) => {
        let timer;
        return (...args) => {
          clearTimeout(timer);
          timer = setTimeout(() => fn(...args), delay);
        };
      };
      const defaultSrc = preview
        ? preview.dataset.placeholder || preview.src
        : "";
      const defaultUrl = input.dataset.defaultUrl;
      const setStatus = (cls, title = "") => {
        status.textContent = "";
        status.className = "url-status" + (cls ? ` ${cls}` : "");
        status.title = title || "URL test result";
      };

      const check = async () => {
        const url = input.value.trim();
        setStatus("");
        if (preview) preview.src = url || defaultSrc;
        if (submit) submit.disabled = true;
        if (!url) return;
        controller?.abort();
        controller = new AbortController();
        setStatus("pending", "Testing...");
        try {
          const res = await fetch(
            `/templates/test_url?url=${encodeURIComponent(url)}`,
            {
              signal: controller.signal,
            },
          );
          const data = await res.json();
          if (res.ok && data.ok) {
            setStatus("ok", "URL reachable");
            if (submit) submit.disabled = false;
          } else {
            const msg = data.status
              ? `HTTP ${data.status}`
              : data.error || "Unreachable";
            setStatus("bad", msg);
            if (submit) submit.disabled = true;
          }
          sendTelemetry("url_test", { url, ok: data.ok });
        } catch {
          if (controller.signal.aborted) return;
          setStatus("bad", "Unreachable");
          if (submit) submit.disabled = true;
          sendTelemetry("url_test", { url, ok: false });
        }
      };

      const checkDebounced = debounce(check, 500);

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
        const hasValue = input.value.trim() !== "";
        setStatus(hasValue ? "pending" : "", hasValue ? "Testing..." : "");
        if (submit) submit.disabled = true;
        if (hasValue) checkDebounced();
      });
      input.addEventListener("paste", () => {
        setTimeout(() => {
          setStatus("pending", "Testing...");
          checkDebounced();
        }, 0);
      });
      input.addEventListener("blur", check);
      input.addEventListener("change", () => {
        check();
      });
    });
  });
}
