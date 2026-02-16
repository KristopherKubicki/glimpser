import { initClocks } from "./clock.js";

export function initNav() {
  document.addEventListener("DOMContentLoaded", () => {
    const healthStatus = document.getElementById("health-status");
    const healthAlwaysVisible =
      healthStatus && healthStatus.dataset.alwaysVisible === "true";
    if (healthStatus && !healthAlwaysVisible) {
      healthStatus.style.display = "none";
    }
    const dangerStatus = document.getElementById("danger-status");
    const discoveryStatus = document.getElementById("discover-status");
    const onSettingsPage = window.location.pathname.startsWith("/settings");
    if (discoveryStatus) {
      discoveryStatus.style.display = onSettingsPage ? "flex" : "none";
    }
    const nav = document.querySelector("nav");
    const groupDropdown = document.getElementById("nav-group-dropdown");
    const cameraDropdown = document.getElementById("nav-camera-dropdown");
    let currentGroup =
      typeof window.currentGroup === "string" && window.currentGroup
        ? window.currentGroup
        : null;
    let currentCamera =
      typeof window.currentCamera === "string" && window.currentCamera
        ? window.currentCamera
        : null;
    const liveLink = document.getElementById("live");

    const updateLiveLinkHref = () => {
      if (!liveLink) return;
      if (currentCamera) {
        liveLink.href = `/live?camera=${encodeURIComponent(currentCamera)}`;
      } else if (currentGroup && currentGroup !== "all") {
        liveLink.href = `/live?group=${encodeURIComponent(currentGroup)}`;
      } else {
        liveLink.href = "/live";
      }
    };

    const syncNavSelections = () => {
      if (groupDropdown && currentGroup) {
        const hasGroup = Array.from(groupDropdown.options || []).some(
          (opt) => opt.value === currentGroup,
        );
        if (hasGroup) groupDropdown.value = currentGroup;
      }
      if (cameraDropdown && currentCamera) {
        const hasCamera = Array.from(cameraDropdown.options || []).some(
          (opt) => opt.value === currentCamera,
        );
        if (hasCamera) cameraDropdown.value = currentCamera;
      }
    };

    window.setLiveNavContext = ({ camera = null, group = null } = {}) => {
      currentCamera = camera || null;
      currentGroup = group && group !== "all" ? group : null;
      window.currentCamera = currentCamera;
      window.currentGroup = currentGroup;
      updateLiveLinkHref();
      syncNavSelections();
    };

    updateLiveLinkHref();
    const menuToggle = document.getElementById("menu-toggle");

    if (nav && menuToggle) {
      menuToggle.addEventListener("click", () => {
        nav.classList.toggle("active");
      });
      nav.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
          nav.classList.remove("active");
        });
      });
    }

    const fetchJson = async (url) => {
      const res = await fetch(url);
      const type = res.headers.get("content-type") || "";
      if (!res.ok || !type.includes("application/json")) {
        return null;
      }
      return res.json();
    };

    const loadNavGroups = async () => {
      if (!groupDropdown) return;
      groupDropdown.innerHTML = '<option value="">Loading...</option>';
      groupDropdown.disabled = true;
      try {
        const groups = await fetchJson("/groups");
        groupDropdown.innerHTML = '<option value="">Groups</option>';
        if (groups && Array.isArray(groups)) {
          groups.forEach((g) => {
            const opt = document.createElement("option");
            opt.value = g;
            opt.textContent = g === "all" ? "All" : g;
            groupDropdown.appendChild(opt);
          });
        }
        if (currentGroup) {
          groupDropdown.value = currentGroup;
          await loadNavCameras(currentGroup);
          if (cameraDropdown && currentCamera) {
            cameraDropdown.value = currentCamera;
          }
          if (typeof window.updateCameraOptions === "function") {
            window.updateCameraOptions(currentGroup);
          }
        }
        updateLiveLinkHref();
      } catch (error) {
        console.error("Error loading groups:", error);
      } finally {
        groupDropdown.disabled = false;
      }
    };

    // Track the most recent camera list request to avoid race conditions
    let cameraRequestId = 0;

    const loadNavCameras = async (group) => {
      if (!cameraDropdown) return;
      const requestId = ++cameraRequestId;
      if (!group || group === "all") {
        cameraDropdown.style.display = "none";
        return;
      }
      cameraDropdown.style.display = "";
      cameraDropdown.innerHTML =
        '<option value="">Cameras</option><option value="__all_rotator__">All Rotator</option>';
      cameraDropdown.disabled = true;
      try {
        const cams = await fetchJson(
          `/templates?group=${encodeURIComponent(group)}`,
        );
        // Ignore this response if a newer request was triggered
        if (requestId !== cameraRequestId) return;
        if (cams) {
          Object.keys(cams)
            .sort()
            .forEach((c) => {
              const opt = document.createElement("option");
              opt.value = c;
              opt.textContent = c;
              cameraDropdown.appendChild(opt);
            });
        }
      } catch (error) {
        console.error("Error loading cameras:", error);
      } finally {
        if (requestId === cameraRequestId) {
          cameraDropdown.disabled = false;
        }
      }
    };

    if (groupDropdown) {
      groupDropdown.addEventListener("change", () => {
        const selected = groupDropdown.value || "all";
        currentGroup = selected === "all" ? null : selected;
        currentCamera = null;
        updateLiveLinkHref();

        // Group selection is always a wall view: All => home wall, group => group wall.
        if (selected === "all") {
          window.location.href = "/";
        } else {
          window.location.href = `/group/${encodeURIComponent(selected)}`;
        }
      });
      if (currentGroup) loadNavCameras(currentGroup);
    }

    if (cameraDropdown) {
      cameraDropdown.addEventListener("change", () => {
        const selectedCamera = cameraDropdown.value || null;
        currentCamera = selectedCamera;
        const activeGroup = groupDropdown ? groupDropdown.value : null;
        currentGroup =
          activeGroup && activeGroup !== "all" ? activeGroup : null;
        updateLiveLinkHref();

        // On /live, tile_player.js handles this selector directly.
        if (window.location.pathname.startsWith("/live")) {
          return;
        }

        if (selectedCamera === "__all_rotator__") {
          currentCamera = null;
          currentGroup = null;
          updateLiveLinkHref();
          window.location.href = "/live";
          return;
        }

        // Outside /live, selecting a camera should always land in live view.
        if (selectedCamera) {
          window.location.href = `/live?camera=${encodeURIComponent(selectedCamera)}`;
          return;
        }

        // "Cameras" (blank option) means rotate by current group/all on live.
        if (currentGroup) {
          window.location.href = `/live?group=${encodeURIComponent(currentGroup)}`;
        } else {
          window.location.href = "/live";
        }
      });
    }

    const checkHealth = async () => {
      if (!healthStatus) return;
      try {
        const data = await fetchJson("/health");
        if (!data) return;
        if (data.status === "healthy") {
          healthStatus.style.color = "green";
          healthStatus.title = "Status: Healthy\n\n";
          if (!healthAlwaysVisible) {
            healthStatus.style.display = "none";
          } else {
            healthStatus.style.display = "flex";
          }
        } else {
          healthStatus.style.display = "flex";
          healthStatus.style.color = "red";
          healthStatus.title = "Status: Degraded\n\n";
        }
        healthStatus.title +=
          `CPU: ${data.metrics.cpu_usage}%\n` +
          `Memory: ${data.metrics.memory_usage}%\n` +
          `Disk: ${data.metrics.disk_usage}%\n` +
          `Open Files: ${data.metrics.open_files}\n` +
          `Threads: ${data.metrics.thread_count}\n` +
          `Uptime: ${data.metrics.uptime}\n`;
        if (data.error_messages?.length) {
          healthStatus.title += `\nErrors:\n${data.error_messages.join("\n")}`;
        }
      } catch (error) {
        console.error("Error fetching health status:", error);
        healthStatus.style.color = "red";
        healthStatus.title = "Error: Unable to fetch health status";
      }
    };

    const checkDanger = async () => {
      if (!dangerStatus) return;
      try {
        const data = await fetchJson("/danger_status");
        if (!data) return;
        if (data.ready) {
          dangerStatus.style.display = "flex";
          dangerStatus.style.color = "orange";
          dangerStatus.title = "Danger Mode Ready";
        } else {
          dangerStatus.style.display = "none";
          const reason = [];
          if (!data.port_open) reason.push("Debug port closed");
          if (!data.idle) reason.push("User active");
          dangerStatus.title = "Danger Mode Off";
          if (reason.length) dangerStatus.title += `\n${reason.join(", ")}`;
        }
      } catch (error) {
        console.error("Error fetching danger status:", error);
      }
    };

    const captionsIcon = document.getElementById("captions");
    const captionChyron = document.getElementById("caption-chyron");
    let chyronSpeed = captionChyron
      ? parseFloat(captionChyron.dataset.speed || "0")
      : 0;
    if (captionChyron && chyronSpeed > 0) {
      captionChyron.style.setProperty("--chyron-speed", `${chyronSpeed}s`);
    }
    window.updateChyron = async (speed) => {
      if (!captionChyron) return;
      chyronSpeed = speed;
      captionChyron.dataset.speed = speed;
      captionChyron.style.setProperty("--chyron-speed", `${speed}s`);
      if (speed > 0) {
        const data = await fetchJson("/captions_status");
        if (data && data.caption) {
          showCaption(data.caption);
        }
      } else {
        captionChyron.classList.remove("show");
      }
    };
    let lastCaptionTime = null;

    let idle = false;
    let idleTimer;
    let pendingCaption = null;
    const idleDelay = 3000; // ms

    const markIdle = () => {
      idle = true;
      if (pendingCaption) {
        showCaption(pendingCaption);
        pendingCaption = null;
      }
    };

    const resetIdleTimer = () => {
      idle = false;
      clearTimeout(idleTimer);
      idleTimer = setTimeout(markIdle, idleDelay);
    };

    ["mousemove", "keydown", "scroll", "touchstart"].forEach((evt) => {
      document.addEventListener(evt, resetIdleTimer);
    });

    resetIdleTimer();

    if (captionChyron) {
      captionChyron.addEventListener("click", () => {
        window.location.href = "/captions";
      });
    }

    window.addEventListener("showChyron", (e) => {
      if (e.detail) showCaption(e.detail);
    });

    const showCaption = (text) => {
      if (!captionChyron || chyronSpeed <= 0) return;
      captionChyron.innerHTML = `<span>${text}</span>`;
      captionChyron.classList.add("show");
      // Keep the caption visible until a new one arrives
    };

    if (captionsIcon && captionChyron) {
      captionsIcon.addEventListener("mouseenter", () => {
        const text = captionsIcon.dataset.caption;
        if (text) showCaption(text);
      });
      captionsIcon.addEventListener("mouseleave", () => {
        captionChyron.classList.remove("show");
      });
    }

    const checkCaptions = async () => {
      if (!captionsIcon) return;
      try {
        const group = window.currentGroup;
        const url =
          group && group !== "all"
            ? `/captions_status?group=${encodeURIComponent(group)}`
            : "/captions_status";
        const data = await fetchJson(url);
        if (!data) return;
        captionsIcon.dataset.caption = data.caption || "";
        captionsIcon.removeAttribute("title");
        if (data.timestamp) {
          const ts = new Date(data.timestamp.replace(" ", "T") + "Z");
          if (!lastCaptionTime || ts > lastCaptionTime) {
            captionsIcon.classList.add("flash-caption");
            setTimeout(
              () => captionsIcon.classList.remove("flash-caption"),
              5000,
            );
            showCaption(data.caption);
            lastCaptionTime = ts;
          }
          const ageSec = (Date.now() - ts.getTime()) / 1000;
          if (ageSec < 60) {
            captionsIcon.style.color = "green";
          } else if (ageSec < 300) {
            captionsIcon.style.color = "yellow";
          } else if (ageSec > 1800) {
            captionsIcon.style.color = "red";
          } else {
            captionsIcon.style.color = "";
          }
        }
      } catch (error) {
        console.error("Error fetching caption status:", error);
      }
    };

    const checkDiscovery = async () => {
      if (!discoveryStatus) return;
      try {
        const data = await fetchJson("/discovery_status");
        const fmt = (s) => `${Math.round(s / 60)}m`;
        const text = data.status === "none" ? "disabled" : data.status;
        if (data.status === "none") {
          discoveryStatus.style.color = "white";
        } else if (data.status === "running") {
          discoveryStatus.style.color = "orange";
        } else if (data.status === "ready") {
          discoveryStatus.style.color = "green";
        } else if (data.status === "error") {
          discoveryStatus.style.color = "red";
        } else {
          discoveryStatus.style.color = "grey";
        }
        let title = `Background discovery: ${text}`;
        if (data.running_for) {
          title += `\nRunning for ${fmt(data.running_for)}`;
        } else if (Number.isFinite(data.age) && data.status !== "none") {
          title += `\nLast run ${fmt(data.age)} ago`;
        }
        if (data.next_run_in) {
          title += `\nNext in ${fmt(data.next_run_in)}`;
        }
        discoveryStatus.title = title;
      } catch (error) {
        console.error("Error fetching discovery status:", error);
        discoveryStatus.style.color = "red";
      }
    };

    const setupNavFade = () => {
      const header = document.querySelector("header");
      const player = document.querySelector(".video-container");
      if (!header || !player) return;

      let fadeTimeout;
      const showNav = () => {
        header.classList.remove("fade-out");
        clearTimeout(fadeTimeout);
        fadeTimeout = setTimeout(() => header.classList.add("fade-out"), 3000);
      };

      ["mousemove", "scroll"].forEach((evt) => {
        document.addEventListener(evt, showNav);
      });

      showNav();
    };

    const setupSpeechStop = () => {
      const speechIcon = document.getElementById("speech-stop");
      if (!speechIcon || !("speechSynthesis" in window)) return;
      const toggle = () => {
        speechIcon.style.display = window.speechSynthesis.speaking
          ? "flex"
          : "none";
      };
      speechIcon.addEventListener("click", () => {
        window.speechSynthesis.cancel();
        toggle();
      });
      toggle();
      setInterval(toggle, 500);
    };

    const setupCameraNavigation = () => {
      const cameraDropdown = document.getElementById("nav-camera-dropdown");
      if (!cameraDropdown) return;

      const getOptions = () =>
        Array.from(cameraDropdown.options).filter((o) => o.value);

      const gotoCamera = (delta) => {
        const opts = getOptions();
        if (!opts.length) return;
        const idx = opts.findIndex((o) => o.value === cameraDropdown.value);
        const next = (idx + delta + opts.length) % opts.length;
        const cam = opts[next].value;
        cameraDropdown.value = cam;
        if (window.location.pathname.startsWith("/live")) {
          cameraDropdown.dispatchEvent(new Event("change"));
        } else {
          window.location.href = `/templates/${encodeURIComponent(cam)}`;
        }
      };

      document.addEventListener("keydown", (e) => {
        if (
          e.target.tagName === "INPUT" ||
          e.target.tagName === "SELECT" ||
          e.target.tagName === "TEXTAREA" ||
          e.target.isContentEditable
        )
          return;
        if (e.key === "ArrowRight" || e.key === "l") {
          gotoCamera(1);
          e.preventDefault();
        } else if (e.key === "ArrowLeft" || e.key === "j") {
          gotoCamera(-1);
          e.preventDefault();
        }
      });

      let touchStartX = null;
      let touchStartY = null;
      document.addEventListener(
        "touchstart",
        (evt) => {
          const t = evt.touches[0];
          touchStartX = t.clientX;
          touchStartY = t.clientY;
        },
        { passive: true },
      );
      document.addEventListener(
        "touchend",
        (evt) => {
          if (touchStartX === null || touchStartY === null) return;
          const diffX = evt.changedTouches[0].clientX - touchStartX;
          const diffY = evt.changedTouches[0].clientY - touchStartY;
          if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY)) {
            if (diffX > 0) gotoCamera(-1);
            else gotoCamera(1);
          }
          touchStartX = null;
          touchStartY = null;
        },
        { passive: true },
      );
    };

    loadNavGroups().then(setupCameraNavigation);
    checkHealth();
    setInterval(checkHealth, 5000);
    checkDanger();
    setInterval(checkDanger, 5000);
    checkCaptions();
    setInterval(checkCaptions, 10000);
    if (discoveryStatus && onSettingsPage) {
      checkDiscovery();
      setInterval(checkDiscovery, 60000);
    }
    initClocks();
    setupNavFade();
    setupSpeechStop();
  });
}
