function setupTemplateForm(container) {
  const urlInput = container.querySelector(".url-input");
  const testBtn = container.querySelector(".url-test-btn");
  const frequencyInput = container.querySelector("#frequency");
  const timeoutInput = container.querySelector("#timeout");
  const presetButtons = container.querySelectorAll(".preset-btn");
  const modeButtons = container.querySelectorAll(".mode-btn");
  const authToggle = container.querySelector("#auth_enabled");
  const authFields = container.querySelectorAll("[data-auth-fields]");
  const browserToggle = container.querySelector("#browser");
  const headlessToggle = container.querySelector("#headless");
  const stealthToggle = container.querySelector("#stealth");
  const eventBufferToggle = container.querySelector("#event_buffer_enabled");
  const eventBufferSection = container.querySelector(".event-buffer-section");
  const eventBufferFields = container.querySelectorAll(
    "[data-event-buffer-field]",
  );
  const eventBufferTestBtn = container.querySelector("#event_buffer_test");
  const eventBufferStatusBtn = container.querySelector("#event_buffer_status");
  const eventBufferTestResult = container.querySelector(
    "#event_buffer_test_result",
  );
  const groupInput = container.querySelector("#groups");
  const advanced = container.querySelector(".advanced-settings");
  const previewItems = {};
  container.querySelectorAll("[data-preview]").forEach((node) => {
    previewItems[node.dataset.preview] = node;
  });

  const setActive = (nodes, match) => {
    nodes.forEach((node) => {
      if (node.dataset[match.key] === match.value) {
        node.classList.add("active");
      } else {
        node.classList.remove("active");
      }
    });
  };

  if (testBtn && urlInput) {
    testBtn.addEventListener("click", () => {
      urlInput.dispatchEvent(new Event("change", { bubbles: true }));
      urlInput.blur();
    });
  }

  presetButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const freq = btn.dataset.frequency;
      const timeout = btn.dataset.timeout;
      if (frequencyInput && freq) frequencyInput.value = freq;
      if (timeoutInput && timeout) timeoutInput.value = timeout;
      if (freq) setActive(presetButtons, { key: "frequency", value: freq });
      if (frequencyInput) {
        frequencyInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (timeoutInput) {
        timeoutInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  });

  const formatValue = (value, fallback = "—") => {
    if (!value) return fallback;
    return value;
  };

  const shortenUrl = (value) => {
    if (!value) return "—";
    if (value.length <= 38) return value;
    return `${value.slice(0, 22)}…${value.slice(-10)}`;
  };

  const updateSummary = () => {
    if (previewItems.url) {
      previewItems.url.textContent = shortenUrl(urlInput?.value.trim());
      previewItems.url.title = urlInput?.value.trim() || "";
    }
    if (previewItems.mode) {
      previewItems.mode.textContent = browserToggle?.checked
        ? "Web Page"
        : "Direct Stream";
    }
    if (previewItems.frequency) {
      previewItems.frequency.textContent = frequencyInput?.value
        ? `${frequencyInput.value} min`
        : "—";
    }
    if (previewItems.timeout) {
      previewItems.timeout.textContent = timeoutInput?.value
        ? `${timeoutInput.value} sec`
        : "—";
    }
    if (previewItems.group) {
      previewItems.group.textContent = formatValue(groupInput?.value, "None");
    }
    if (previewItems.auth) {
      previewItems.auth.textContent = authToggle?.checked ? "On" : "Off";
    }
  };

  const syncEventBuffer = () => {
    if (!eventBufferToggle) return;
    const incompatible =
      Boolean(browserToggle?.checked) || Boolean(stealthToggle?.checked);
    if (incompatible) {
      eventBufferToggle.checked = false;
    }
    eventBufferToggle.disabled = incompatible;
    const enabled = eventBufferToggle.checked && !incompatible;
    eventBufferFields.forEach((field) => {
      field.disabled = !enabled;
    });
    if (eventBufferSection) {
      eventBufferSection.classList.toggle("is-disabled", !enabled);
    }
  };

  const applyMode = (mode) => {
    if (mode === "stream") {
      if (browserToggle) browserToggle.checked = false;
      if (headlessToggle) headlessToggle.checked = false;
      if (stealthToggle) stealthToggle.checked = false;
      setActive(modeButtons, { key: "mode", value: "stream" });
    }
    if (mode === "web") {
      if (browserToggle) browserToggle.checked = true;
      if (headlessToggle) headlessToggle.checked = true;
      if (stealthToggle) stealthToggle.checked = false;
      if (advanced) advanced.open = true;
      setActive(modeButtons, { key: "mode", value: "web" });
    }
    syncEventBuffer();
    updateSummary();
  };

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      applyMode(btn.dataset.mode);
    });
  });

  const inferModeFromUrl = (value) => {
    if (!value) return null;
    const url = value.toLowerCase();
    if (url.startsWith("rtsp://")) return "stream";
    try {
      const host = new URL(url).hostname;
      if (
        ["youtube.com", "youtu.be"].some(
          (domain) => host === domain || host.endsWith(`.${domain}`),
        )
      )
        return "stream";
    } catch {
      return null;
    }
    if (url.endsWith(".mjpg") || url.includes("mjpg")) return "stream";
    if (
      url.endsWith(".jpg") ||
      url.endsWith(".png") ||
      url.includes("snapshot")
    ) {
      return "stream";
    }
    return null;
  };

  const normalizeUrl = () => {
    if (!urlInput) return;
    const value = urlInput.value.trim();
    if (!value) return;
    if (!value.includes("://")) {
      urlInput.value = `https://${value}`;
    }
  };

  const syncAuth = () => {
    const enabled = authToggle ? authToggle.checked : false;
    authFields.forEach((row) => {
      if (enabled) {
        row.classList.remove("hidden");
        row.querySelectorAll("input").forEach((input) => {
          input.disabled = false;
        });
      } else {
        row.classList.add("hidden");
        row.querySelectorAll("input").forEach((input) => {
          input.disabled = true;
        });
      }
    });
  };

  if (authToggle) {
    authToggle.addEventListener("change", syncAuth);
    syncAuth();
  }

  if (eventBufferToggle) {
    eventBufferToggle.addEventListener("change", syncEventBuffer);
    syncEventBuffer();
  }

  if (stealthToggle) {
    stealthToggle.addEventListener("change", syncEventBuffer);
  }

  if (browserToggle) {
    browserToggle.addEventListener("change", syncEventBuffer);
  }

  if (eventBufferTestBtn && eventBufferSection) {
    eventBufferTestBtn.addEventListener("click", async () => {
      const testUrl = eventBufferSection.dataset.eventBufferTestUrl;
      const form = eventBufferTestBtn.closest("form");
      if (!testUrl || !form) {
        if (eventBufferTestResult) {
          eventBufferTestResult.textContent = "BLOCKED: save first";
        }
        return;
      }

      if (eventBufferTestResult) {
        eventBufferTestResult.textContent = "Testing...";
      }
      const body = new FormData(form);
      if (!eventBufferToggle?.checked) {
        body.set("event_buffer_enabled", "false");
      }
      try {
        const response = await fetch(testUrl, {
          method: "POST",
          body,
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (eventBufferTestResult) {
          const status = response.ok ? "OK" : "BLOCKED";
          eventBufferTestResult.textContent = `${status}: ${
            payload.message || payload.status || "unknown"
          }`;
        }
      } catch (error) {
        if (eventBufferTestResult) {
          eventBufferTestResult.textContent = "BLOCKED: test failed";
        }
      }
    });
  }

  const eventBufferAge = (timestamp) => {
    if (!timestamp) return "never";
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
    if (seconds < 90) return `${seconds}s ago`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 90) return `${minutes}m ago`;
    return `${Math.round(minutes / 60)}h ago`;
  };

  if (eventBufferStatusBtn && eventBufferSection) {
    eventBufferStatusBtn.addEventListener("click", async () => {
      const statusUrl = eventBufferSection.dataset.eventBufferStatusUrl;
      if (!statusUrl) {
        if (eventBufferTestResult) {
          eventBufferTestResult.textContent = "STATUS: save first";
        }
        return;
      }

      if (eventBufferTestResult) {
        eventBufferTestResult.textContent = "Checking...";
      }
      try {
        const response = await fetch(statusUrl, {
          method: "GET",
          credentials: "same-origin",
        });
        const payload = await response.json();
        const frames = payload.frames || 0;
        const parts = [`${frames} frames`];
        if (payload.newest)
          parts.push(`newest ${eventBufferAge(payload.newest)}`);
        if (
          payload.backoff_until &&
          payload.backoff_until > Date.now() / 1000
        ) {
          parts.push(
            `backoff ${Math.ceil(payload.backoff_until - Date.now() / 1000)}s`,
          );
        }
        if (payload.last_error) parts.push(payload.last_error);
        if (eventBufferTestResult) {
          eventBufferTestResult.textContent = `${
            response.ok ? "STATUS" : "BLOCKED"
          }: ${parts.join(", ")}`;
        }
      } catch (error) {
        if (eventBufferTestResult) {
          eventBufferTestResult.textContent = "STATUS: check failed";
        }
      }
    });
  }

  if (frequencyInput) {
    const freq = frequencyInput.value;
    if (freq) setActive(presetButtons, { key: "frequency", value: freq });
  }

  if (browserToggle) {
    applyMode(browserToggle.checked ? "web" : "stream");
  }

  if (urlInput) {
    urlInput.addEventListener("blur", () => {
      normalizeUrl();
      const inferred = inferModeFromUrl(urlInput.value);
      if (inferred) applyMode(inferred);
      updateSummary();
    });
    urlInput.addEventListener("input", updateSummary);
  }

  if (frequencyInput) {
    frequencyInput.addEventListener("input", updateSummary);
  }

  if (timeoutInput) {
    timeoutInput.addEventListener("input", updateSummary);
  }

  if (groupInput) {
    groupInput.addEventListener("input", updateSummary);
  }

  if (authToggle) {
    authToggle.addEventListener("change", updateSummary);
  }

  updateSummary();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".edit-template-container").forEach((container) => {
    setupTemplateForm(container);
  });
});
