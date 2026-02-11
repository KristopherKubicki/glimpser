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
    if (url.includes("youtube.com") || url.includes("youtu.be"))
      return "stream";
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
