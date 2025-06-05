export function initNav() {
  document.addEventListener("DOMContentLoaded", () => {
    const healthStatus = document.getElementById("health-status");
    const dangerStatus = document.getElementById("danger-status");
    const discoveryStatus = document.getElementById("discover-status");
    const nav = document.querySelector("nav");
    const menuToggle = document.getElementById("menu-toggle");
    const groupDropdown = document.getElementById("nav-group-dropdown");
    const cameraDropdown = document.getElementById("nav-camera-dropdown");
    const currentGroup = window.currentGroup || null;
    const currentCamera = window.currentCamera || null;

    if (nav && menuToggle) {
      menuToggle.addEventListener("click", () => {
        nav.classList.toggle("active");
      });
    }

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
        }
      } catch (error) {
        console.error("Error loading groups:", error);
      } finally {
        groupDropdown.disabled = false;
      }
    };

    const loadNavCameras = async (group) => {
      if (!cameraDropdown) return;
      if (!group || group === "all") {
        cameraDropdown.style.display = "none";
        return;
      }
      cameraDropdown.style.display = "";
      cameraDropdown.innerHTML = '<option value="">Cameras</option>';
      cameraDropdown.disabled = true;
      try {
        const cams = await fetchJson(`/templates?group=${encodeURIComponent(group)}`);
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
        cameraDropdown.disabled = false;
      }
    };

    if (groupDropdown) {
      groupDropdown.addEventListener("change", () => {
        if (!groupDropdown.value) return;
        if (groupDropdown.value === "all") {
          window.location.href = "/";
        } else {
          window.location.href = `/group/${encodeURIComponent(
            groupDropdown.value,
          )}`;
        }
        loadNavCameras(groupDropdown.value);
      });
      if (currentGroup) loadNavCameras(currentGroup);
    }

    if (cameraDropdown) {
      cameraDropdown.addEventListener("change", () => {
        if (cameraDropdown.value) {
          window.location.href = `/templates/${encodeURIComponent(
            cameraDropdown.value,
          )}`;
        }
      });
    }

    /**
     * Fetch JSON from an endpoint. If the response is not JSON or the
     * request fails, an error is thrown so callers can handle it.
     */
    const fetchJson = async (url) => {
      const res = await fetch(url);
      const type = res.headers.get("content-type") || "";
      if (!res.ok || !type.includes("application/json")) {
        return null;
      }
      return res.json();
    };

    const checkHealth = async () => {
      if (!healthStatus) return;
      try {
        const data = await fetchJson("/health");
        if (!data) return;
        if (data.status === "healthy") {
          healthStatus.style.color = "green";
          healthStatus.title = "System Status: Healthy\n\n";
        } else {
          healthStatus.style.color = "red";
          healthStatus.title = "System Status: Degraded\n\n";
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
    const chyronSpeed = captionChyron
      ? parseFloat(captionChyron.dataset.speed || "0")
      : 0;
    if (captionChyron && chyronSpeed > 0) {
      captionChyron.style.setProperty("--chyron-speed", `${chyronSpeed}s`);
    }
    let lastCaptionTime = null;
    let popupTimer;

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

    const showCaption = (text) => {
      if (!captionChyron || chyronSpeed <= 0) return;
      captionChyron.innerHTML = `<span>${text}</span>`;
      captionChyron.classList.add("show");
      clearTimeout(popupTimer);
      popupTimer = setTimeout(
        () => captionChyron.classList.remove("show"),
        chyronSpeed * 1000,
      );
    };

    const checkCaptions = async () => {
      if (!captionsIcon) return;
      try {
        const data = await fetchJson("/captions_status");
        if (!data) return;
        captionsIcon.title = data.caption || "";
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
        let title = `Background discovery: ${data.status}`;
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

    const updateCoolClock = () => {
      const secondHand = document.querySelector(".second-hand");
      const minuteHand = document.querySelector(".minute-hand");
      const hourHand = document.querySelector(".hour-hand");
      const digitalTime = document.getElementById("digitalTime");
      if (!secondHand || !minuteHand || !hourHand || !digitalTime) return;

      const now = new Date();
      const secondsDegrees = (now.getSeconds() / 60) * 360;
      const minutesDegrees =
        (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
      const hoursDegrees =
        (now.getHours() / 12) * 360 + (now.getMinutes() / 60) * 30;

      secondHand.style.transform = `rotate(${secondsDegrees}deg)`;
      minuteHand.style.transform = `rotate(${minutesDegrees}deg)`;
      hourHand.style.transform = `rotate(${hoursDegrees}deg)`;

      digitalTime.title = `${now.toLocaleTimeString()}\n${Intl.DateTimeFormat().resolvedOptions().timeZone}\n${now.toDateString()}`;
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

    loadNavGroups();
    checkHealth();
    setInterval(checkHealth, 5000);
    checkDanger();
    setInterval(checkDanger, 5000);
    checkCaptions();
    setInterval(checkCaptions, 10000);
    checkDiscovery();
    setInterval(checkDiscovery, 60000);
    updateCoolClock();
    setInterval(updateCoolClock, 1000);
    setupNavFade();
  });
}
