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
      const overlay = container
        ? container.querySelector(".preview-status")
        : document.querySelector(".preview-status");
      if (!status) return;

      const form = input.closest("form");
      const controlled = [];
      let submit;
      let urlOk = false;
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
        if (submit) {
          submit.disabled = disable;
          if (disable) {
            submit.classList.remove("confirm-submit");
            delete submit.dataset.urlOk;
          }
        }
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
      const player = document.getElementById("live-video");
      const playerSource = player ? player.querySelector("source") : null;
      const defaultUrl = input.dataset.defaultUrl;
      const setStatus = (cls, title = "") => {
        status.textContent = "";
        status.className = "url-status" + (cls ? ` ${cls}` : "");
        status.title = title || "URL test result";
      };

      const showOverlay = (msg) => {
        if (!overlay) return;
        overlay.textContent = msg;
        overlay.style.display = msg ? "flex" : "none";
      };

      const formatTitle = (data) => {
        if (!data.ok) {
          return (
            data.error || (data.status ? `HTTP ${data.status}` : "Unreachable")
          );
        }
        let t = data.status ? `HTTP ${data.status}` : "OK";
        if (data.content_type) {
          t += ` \u00b7 ${data.content_type}`;
        }
        return t;
      };

      const check = async () => {
        const url = input.value.trim();
        setStatus("");
        showOverlay("");
        if (preview) preview.src = url || defaultSrc;
        if (submit) submit.disabled = true;
        if (!url) return;
        controller?.abort();
        controller = new AbortController();
        setStatus("pending", "Testing...");
        showOverlay("Testing...");
        try {
          const res = await fetch(
            `/templates/test_url?url=${encodeURIComponent(url)}`,
            {
              signal: controller.signal,
            },
          );
          const data = await res.json();
          const title = formatTitle(data);
          const sugg = data.suggestions || {};
          const setCheck = (id, val) => {
            const el = container
              ? container.querySelector(`#${id}`)
              : document.getElementById(id);
            if (el && typeof val === "boolean") el.checked = val;
          };
          if (res.ok && data.ok) {
            urlOk = true;
            setStatus("ok", title);
            showOverlay("");
            if (submit) {
              submit.disabled = false;
              submit.classList.remove("confirm-submit");
              submit.dataset.urlOk = "true";
            }
          } else {
            urlOk = false;
            setStatus("bad", title);
            showOverlay(title);
            if (preview) preview.src = defaultSrc;
            if (player) {
              player.pause();
              if (playerSource) {
                playerSource.removeAttribute("src");
              } else {
                player.removeAttribute("src");
              }
              player.poster = defaultSrc;
              player.load();
            }
            if (submit) {
              submit.disabled = false;
              submit.classList.add("confirm-submit");
              submit.dataset.urlOk = "false";
            }
          }
          setCheck("browser", sugg.browser);
          setCheck("headless", sugg.headless);
          setCheck("stealth", sugg.stealth);
          sendTelemetry("url_test", { url, ok: data.ok });
        } catch {
          if (controller.signal.aborted) return;
          urlOk = false;
          setStatus("bad", "Unreachable");
          showOverlay("Unreachable");
          if (preview) preview.src = defaultSrc;
          if (player) {
            player.pause();
            if (playerSource) {
              playerSource.removeAttribute("src");
            } else {
              player.removeAttribute("src");
            }
            player.poster = defaultSrc;
            player.load();
          }
          if (submit) {
            submit.disabled = false;
            submit.classList.add("confirm-submit");
            submit.dataset.urlOk = "false";
          }
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
        showOverlay(hasValue ? "Testing..." : "");
        if (submit) {
          submit.disabled = true;
          submit.classList.remove("confirm-submit");
          delete submit.dataset.urlOk;
        }
        if (hasValue) checkDebounced();
      });
      input.addEventListener("paste", () => {
        setTimeout(() => {
          setStatus("pending", "Testing...");
          showOverlay("Testing...");
          if (submit) {
            submit.classList.remove("confirm-submit");
            delete submit.dataset.urlOk;
          }
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
