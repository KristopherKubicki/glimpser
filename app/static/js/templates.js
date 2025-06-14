import { enqueueClip } from "./video.js";

export const NO_TIMESTAMP_PLACEHOLDER = "no timestamp";

function safePlay(el) {
  const promise = el.play();
  if (promise && typeof promise.catch === "function") {
    promise.catch((err) => {
      // Ignore common interrupt errors so console output stays clean
      if (err.name !== "AbortError" && err.name !== "NotAllowedError") {
        console.error("Error playing video:", err);
      }
    });
  }
}

function createTemplateCard(name, template, index, mobile) {
  const lastScreenshotTime =
    template.last_screenshot_time || NO_TIMESTAMP_PLACEHOLDER;
  const humanizedTimestamp =
    lastScreenshotTime === NO_TIMESTAMP_PLACEHOLDER
      ? NO_TIMESTAMP_PLACEHOLDER
      : timeAgo(lastScreenshotTime);
  const lastScreenshotDate = new Date(lastScreenshotTime);
  const ageMinutes = (Date.now() - lastScreenshotDate.getTime()) / 60000;
  const videoContainerClass = "video-container";
  const errorClass = template.capture_failed
    ? "template-error"
    : "recent-screenshot";
  const borderColor = computeBorderColor(ageMinutes, template.capture_failed);

  const div = document.createElement("div");
  div.classList.add("templateDiv");
  if (mobile) div.classList.add("mobile-card");
  div.style.opacity = "0";
  div.style.transform = "translateY(20px)";
  div.style.transition = "opacity 0.5s ease, transform 0.5s ease";

  div.dataset.name = name;
  div.dataset.index = index.toString();
  div.dataset.last = template.last_screenshot_time || "";
  div.dataset.next = template.next_screenshot_time || "";
  div.dataset.error = template.capture_failed ? "1" : "0";

  div.innerHTML = `
    <a href='/templates/${name}'>
      <div class="${videoContainerClass} ${errorClass}" data-timestamp="${lastScreenshotTime}" style="border-color: ${borderColor}">
        <div class="camera-name">${name}</div>
        <div class="loading-spinner" aria-hidden="true"></div>
        <video data-name="${name}" data-poster="/last_screenshot/${name}" alt="${name}" style="width:100%" muted title="${template.last_caption} (${humanizedTimestamp})" preload="none" disableRemotePlayback data-hd-src="/clip/${name}" loading="lazy">
          <source src="/last_video/${name}" type="video/mp4">
          Your browser does not support the video tag.
        </video>
        <div class="caption-overlay">${template.last_caption || ""}</div>
      </div>
    </a>
    <a href='${template.url}' target='_blank' class='open-url-link' title='Open monitored page' aria-label='Open monitored page'>↗</a>
    <button class='delete-camera-btn advanced-only' onclick="window.confirmDeleteCamera('${name}')" title='Delete this camera' aria-label='Delete camera'>✖</button>
  `;
  return div;
}

let captionsVisible = localStorage.getItem("showCaptions") !== "false";

export function setCaptionsVisibility(value) {
  const slider = document.getElementById("grid-width-slider");
  captionsVisible = value;
  localStorage.setItem("showCaptions", value.toString());
  applyCaptionVisibility(parseFloat(slider?.value || "0"));
  updateTableLayout(parseFloat(slider?.value || "0"));
}

export function applyCaptionVisibility(width) {
  const templateList = document.getElementById("template-list");
  const captionToggle = document.getElementById("caption-toggle");
  const enabled = !width || width >= 150;
  const show = captionsVisible && enabled;
  document.documentElement.classList.toggle("hide-captions", !show);
  templateList
    ?.querySelectorAll(".caption-overlay")
    .forEach((o) => (o.style.display = show ? "block" : "none"));
  if (captionToggle) {
    captionToggle.classList.toggle("disabled", !enabled);
    captionToggle.classList.toggle("active", captionsVisible && enabled);
    captionToggle.classList.toggle("off", !captionsVisible && enabled);
    captionToggle.title = enabled
      ? captionsVisible
        ? "Hide caption overlays"
        : "Show caption overlays"
      : "Increase tile size to enable captions";
  }
}

function updateTableLayout(width) {
  const rows = document.querySelectorAll("#camera-table .camera-row");
  rows.forEach((row) => {
    const preview = row.querySelector(".templateDiv");
    if (!preview) return;
    const height = preview.offsetHeight;
    row.style.height = `${height}px`;
    const caption = row.querySelector(".last-caption");
    if (caption) {
      caption.classList.toggle("hidden", width < 150);
    }
  });
}

export function initTemplates() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#template-form form");
    const groupDropdown = document.getElementById("group-dropdown");
    const groupsSelect = document.getElementById("groups");
    const templateDetails = document
      .getElementById("template-form")
      ?.closest("details");
    const slider = document.getElementById("grid-width-slider");
    const isMobile = window.matchMedia(
      "(hover: none) and (max-width: 767px)",
    ).matches;
    const templateList = document.getElementById("template-list");
    const captionToggle = document.getElementById("caption-toggle");
    const MAX_THUMBNAIL_HEIGHT = 1080;
    const ASPECT_RATIO = 9 / 16;
    const MAX_THUMBNAIL_WIDTH = Math.round(MAX_THUMBNAIL_HEIGHT / ASPECT_RATIO);

    if (slider) {
      const updateSliderLimits = () => {
        slider.max = Math.min(window.innerWidth, MAX_THUMBNAIL_WIDTH);
        if (isMobile) {
          slider.min = slider.max;
          slider.value = slider.max;
          document.documentElement.style.setProperty(
            "--tile-size",
            `${slider.value}px`,
          );
          slider.dispatchEvent(new Event("input"));
          return;
        }

        const templateCount =
          templateList?.querySelectorAll(".templateDiv").length || 1;

        const gap = parseFloat(getComputedStyle(templateList).gap || "0") || 0;

        // Iterate over possible column counts to find the largest tile width
        // that fits the viewport horizontally and vertically.
        let bestWidth = 50;
        const headerHeight =
          document.querySelector("header")?.offsetHeight || 0;
        const bannerHeight =
          document.getElementById("network-banner")?.offsetHeight || 0;
        const footerSpace = parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue(
            "--footer-space",
          ) || "0",
        );
        const availableHeight =
          window.innerHeight - headerHeight - bannerHeight - footerSpace;

        for (let cols = 1; cols <= templateCount; cols++) {
          const maxWidthForCols = Math.floor(
            (window.innerWidth - gap * (cols - 1)) / cols,
          );
          if (maxWidthForCols < 50) break;
          const rows = Math.ceil(templateCount / cols);
          const tileHeight = maxWidthForCols * ASPECT_RATIO;
          const totalHeight = rows * tileHeight + gap * (rows - 1);
          if (totalHeight <= availableHeight && maxWidthForCols > bestWidth) {
            bestWidth = maxWidthForCols;
          }
        }

        const widthForMaxHeight = MAX_THUMBNAIL_HEIGHT / ASPECT_RATIO;
        slider.max = Math.min(slider.max, widthForMaxHeight);

        const computedMin = Math.max(
          50,
          Math.min(slider.max, Math.floor(bestWidth)),
        );

        slider.min = computedMin;
        slider.value = computedMin;
        document.documentElement.style.setProperty(
          "--tile-size",
          `${slider.value}px`,
        );
        slider.dispatchEvent(new Event("input"));
      };

      updateSliderLimits();
      window.addEventListener("resize", updateSliderLimits);
      window.updateSliderLimits = updateSliderLimits;
      slider.dispatchEvent(new Event("input"));
    }

    if (captionToggle) {
      captionToggle.addEventListener("click", () => {
        if (captionToggle.classList.contains("disabled")) return;
        captionsVisible = !captionsVisible;
        localStorage.setItem("showCaptions", captionsVisible.toString());
        applyCaptionVisibility(parseFloat(slider?.value || "0"));
        updateTableLayout(parseFloat(slider?.value || "0"));
      });
      setTimeout(() => {
        captionToggle.classList.add("flash-caption");
        setTimeout(() => captionToggle.classList.remove("flash-caption"), 4000);
      }, 500);
    }

    function autofillGroup() {
      if (groupsSelect && groupDropdown && groupDropdown.value !== "all") {
        groupsSelect.value = groupDropdown.value;
      }
    }

    if (groupDropdown) {
      groupDropdown.addEventListener("change", () => {
        loadTemplates();
        if (templateDetails && templateDetails.open) {
          autofillGroup();
        }
      });
    }

    if (templateDetails) {
      templateDetails.addEventListener("toggle", () => {
        if (templateDetails.open) {
          autofillGroup();
        }
      });
    }

    if (slider && templateList) {
      const handleSlider = () => {
        let value = Math.min(parseFloat(slider.value), MAX_THUMBNAIL_WIDTH);
        const height = Math.min(
          Math.round((value * 9) / 16),
          MAX_THUMBNAIL_HEIGHT,
        );
        document.documentElement.style.setProperty("--tile-size", `${value}px`);
        templateList.querySelectorAll(".templateDiv").forEach((div) => {
          div.style.width = `${value}px`;
          div.style.height = `${height}px`;
        });

        const scale = value / 360;
        const cameraNameFontSize = Math.max(6, 14 * scale);
        const timestampFontSize = Math.max(6, 12 * scale);
        document.documentElement.style.setProperty(
          "--tile-scale",
          scale.toString(),
        );
        document.documentElement.style.setProperty(
          "--camera-name-font-size",
          `${cameraNameFontSize}px`,
        );
        document.documentElement.style.setProperty(
          "--timestamp-font-size",
          `${timestampFontSize}px`,
        );
        applyCaptionVisibility(value);
        updateTableLayout(value);
      };

      slider.addEventListener("input", handleSlider);
      slider.addEventListener("change", handleSlider);
      if (isMobile) {
        slider.style.display = "none";
        slider.value = Math.min(window.innerWidth, slider.max);
        handleSlider();
        window.addEventListener("resize", () => {
          slider.value = Math.min(window.innerWidth, slider.max);
          handleSlider();
        });
      } else {
        handleSlider();
        setupTileResizeDrag(slider);
      }
    }

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        const submitButton = form.querySelector('input[type="submit"]');
        const feedbackElement = document.createElement("div");
        feedbackElement.className = "form-feedback";
        form.appendChild(feedbackElement);

        submitButton.disabled = true;
        submitButton.innerHTML = "Submitting...";
        feedbackElement.textContent = "Submitting form...";

        try {
          const response = await fetch("/templates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          });
          await response.json();
          loadTemplates();
          form.reset();

          feedbackElement.textContent = "Source successfully created!";
          feedbackElement.style.color = "green";
        } catch (error) {
          console.error("Error:", error);
          feedbackElement.textContent = "An error occurred. Please try again.";
          feedbackElement.style.color = "red";
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = "Submit";
          setTimeout(() => feedbackElement.remove(), 3000);
        }
      });
    }

    loadGroups();
    const cameraTable = document.getElementById("camera-table");
    if (!cameraTable) {
      loadTemplates();
    }
    setupSearch();
    setupSorting();
    setupSortMenu();
    setupCaptionsFilter();
    setupStatusFilter();
    updateHumanizedTimes();
    setInterval(updateHumanizedTimes, 60000);
    applyCaptionVisibility(parseFloat(slider?.value || "0"));
    updateTableLayout(parseFloat(slider?.value || "0"));
  });

  window.showStructuredInput = showStructuredInput;
  window.generateXPath = generateXPath;
}

export async function loadGroups() {
  // Support group selection in multiple pages
  const groupDropdown =
    document.getElementById("group-dropdown") ||
    document.getElementById("cost-group");
  const groupsSelect = document.getElementById("groups");
  const groupDatalist = document.getElementById("group-options");
  if (!groupDropdown && !groupsSelect) return;
  if (groupDropdown) {
    groupDropdown.innerHTML = '<option value="all">Loading groups...</option>';
    groupDropdown.disabled = true;
  }
  if (groupsSelect) {
    groupsSelect.disabled = true;
    if (groupDatalist) groupDatalist.innerHTML = "";
  }

  try {
    const response = await fetch("/groups");
    const groups = await response.json();
    if (groupDropdown) {
      groupDropdown.innerHTML = '<option value="all">All Groups</option>';
    }
    if (groupsSelect && groupDatalist) {
      groupDatalist.innerHTML = "";
    }
    groups.forEach((group) => {
      if (groupDropdown) {
        const option = document.createElement("option");
        option.value = group;
        option.textContent = group;
        groupDropdown.appendChild(option);
      }
      if (groupsSelect && groupDatalist) {
        const option = document.createElement("option");
        option.value = group;
        groupDatalist.appendChild(option);
      }
    });
  } catch (error) {
    console.error("Error loading groups:", error);
    if (groupDropdown) {
      groupDropdown.innerHTML = '<option value="all">All Groups</option>';
    }
    if (groupsSelect && groupDatalist) {
      groupDatalist.innerHTML = "";
    }
  } finally {
    if (groupDropdown) groupDropdown.disabled = false;
    if (groupsSelect) groupsSelect.disabled = false;
  }

  // Close the loadGroups function
}

export function getSelectedGroup() {
  const dropdown = document.getElementById("group-dropdown");
  if (dropdown && dropdown.value) return dropdown.value;
  const navDropdown = document.getElementById("nav-group-dropdown");
  if (navDropdown && navDropdown.value) return navDropdown.value;
  if (window.currentGroup) return window.currentGroup;
  return "all";
}

export function timeAgo(dateString) {
  if (!dateString) return "just now";
  const now = new Date();
  const iso =
    dateString instanceof Date
      ? dateString.toISOString()
      : dateString.includes("T")
        ? /Z$|[+-]\d{2}:?\d{2}$/.test(dateString)
          ? dateString
          : `${dateString}Z`
        : `${dateString.replace(" ", "T")}Z`;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "just now";
  const diffInSeconds = Math.floor((now - parsed) / 1000);
  if (diffInSeconds < 0) return "in the future";

  const intervals = [
    { label: "year", short: "y", seconds: 31536000 },
    { label: "month", short: "mo", seconds: 2592000 },
    { label: "day", short: "d", seconds: 86400 },
    { label: "hour", short: "h", seconds: 3600 },
    { label: "minute", short: "m", seconds: 60 },
    { label: "second", short: "s", seconds: 1 },
  ];

  for (const { label, short, seconds } of intervals) {
    const count = Math.floor(diffInSeconds / seconds);
    if (count >= 1) return `${count}${short} ago`;
  }
  return "just now";
}

export function formatExactTime(dateString) {
  const date =
    dateString instanceof Date
      ? dateString
      : new Date(
          dateString.includes("T")
            ? /Z$|[+-]\d{2}:?\d{2}$/.test(dateString)
              ? dateString
              : `${dateString}Z`
            : `${dateString.replace(" ", "T")}Z`,
        );
  return date.toString();
}

export function isMobile() {
  return window.matchMedia("(hover: none) and (max-width: 767px)").matches;
}

export function computeBorderColor(ageMinutes, isError) {
  const base = isError ? [255, 0, 0] : [26, 115, 232];
  let step = 0;
  if (ageMinutes >= 1) {
    step = Math.floor(Math.log10(ageMinutes)) + 1;
  }
  const alpha = Math.pow(0.5, step);
  return `rgba(${base[0]}, ${base[1]}, ${base[2]}, ${alpha})`;
}

export function setupTileResizeDrag(slider) {
  if (!slider) return;
  const handle = document.createElement("div");
  handle.id = "tile-drag-handle";
  document.body.appendChild(handle);

  let startX = 0;
  let startVal = 0;

  const onMove = (e) => {
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const dx = clientX - startX;
    const { width } = slider.getBoundingClientRect();
    const range = parseFloat(slider.max) - parseFloat(slider.min);
    const delta = (dx / width) * range;
    const value = Math.min(
      parseFloat(slider.max),
      Math.max(parseFloat(slider.min), startVal + delta),
    );
    slider.value = value.toString();
    slider.dispatchEvent(new Event("input"));
  };

  const endDrag = () => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("touchmove", onMove);
    document.removeEventListener("mouseup", endDrag);
    document.removeEventListener("touchend", endDrag);
  };

  const startDrag = (e) => {
    startX = e.touches ? e.touches[0].clientX : e.clientX;
    startVal = parseFloat(slider.value);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("touchmove", onMove);
    document.addEventListener("mouseup", endDrag);
    document.addEventListener("touchend", endDrag);
    e.preventDefault();
  };

  handle.addEventListener("mousedown", startDrag);
  handle.addEventListener("touchstart", startDrag);
}

function attachVideoHover(video, name) {
  const scrub = (e) => {
    const rect = video.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const clamped = Math.max(0, Math.min(1, ratio));
    if (!Number.isNaN(video.duration)) {
      video.currentTime = video.duration * clamped;
    }
  };

  let resetTimeout;
  let dwellTimeout;

  video.addEventListener("mouseenter", (e) => {
    clearTimeout(resetTimeout);
    clearTimeout(dwellTimeout);
    video.style.display = "block";
    dwellTimeout = setTimeout(() => {
      const tiles = document.querySelectorAll(".templateDiv").length;
      const width = video.getBoundingClientRect().width;
      if (tiles <= 8 && width >= 200) {
        enqueueClip(video);
      }
    }, 300);
    if (video.readyState === 0) {
      video.load();
    }
    video.pause();
    if (video.readyState >= 1) {
      scrub(e);
    } else {
      const onLoad = () => {
        scrub(e);
        video.removeEventListener("loadedmetadata", onLoad);
      };
      video.addEventListener("loadedmetadata", onLoad);
    }
  });

  video.addEventListener("mousemove", scrub);

  video.addEventListener("mouseleave", () => {
    clearTimeout(dwellTimeout);
    resetTimeout = setTimeout(() => {
      video.pause();
      video.currentTime = 0;
      video.poster = `/last_screenshot/${name}?t=${Date.now()}`;
      video.load();
    }, 1000);
  });
}

export function updateGridLayout() {
  const templateList = document.getElementById("template-list");
  if (!templateList) return;
  if (isMobile()) {
    templateList.style.gridTemplateColumns = "1fr";
  } else {
    templateList.style.gridTemplateColumns =
      "repeat(auto-fit, minmax(50px, var(--tile-size)))";
  }
}

export function templateBelongsToGroup(template, group) {
  if (group === "all") return true;
  const templateGroups = template.groups ? template.groups.split(",") : [];
  return templateGroups.includes(group);
}

export function updateHumanizedTimes() {
  document.querySelectorAll(".humanized-time").forEach((element) => {
    const timestamp = element.getAttribute("data-time");
    if (timestamp) {
      element.textContent = timeAgo(timestamp);
      element.title = formatExactTime(timestamp);
    }
  });

  document
    .querySelectorAll(
      ".video-container[data-timestamp], .templateDiv img[data-timestamp], video.hover-video[data-timestamp]",
    )
    .forEach((element) => {
      const original =
        element.dataset.originalTimestamp ||
        element.getAttribute("data-timestamp");
      if (!element.dataset.originalTimestamp) {
        element.dataset.originalTimestamp = original;
      }
      if (original && original !== NO_TIMESTAMP_PLACEHOLDER) {
        element.setAttribute("data-timestamp", timeAgo(original));
        element.setAttribute("title", formatExactTime(original));
      } else if (original === NO_TIMESTAMP_PLACEHOLDER) {
        element.setAttribute("data-timestamp", NO_TIMESTAMP_PLACEHOLDER);
        element.removeAttribute("title");
      }
    });
}

export function showStructuredInput(inputId) {
  const input = document.getElementById(inputId);
  const structuredInputHtml = `
    <div class="structured-xpath-input">
      <select id="${inputId}_tag">
        <option value="div">div</option>
        <option value="span">span</option>
        <option value="a">a</option>
        <option value="p">p</option>
        <option value="*">*</option>
      </select>
      <select id="${inputId}_attribute">
        <option value="class">class</option>
        <option value="id">id</option>
        <option value="name">name</option>
        <option value="data-*">data-*</option>
      </select>
      <input type="text" id="${inputId}_value" placeholder="Attribute value">
      <button type="button" onclick="generateXPath('${inputId}')">Generate XPath</button>
    </div>
  `;
  input.insertAdjacentHTML("afterend", structuredInputHtml);
  input.style.display = "none";
}

export function generateXPath(inputId) {
  const tag = document.getElementById(`${inputId}_tag`).value;
  const attribute = document.getElementById(`${inputId}_attribute`).value;
  const value = document.getElementById(`${inputId}_value`).value;

  let xpath = `//${tag}`;
  xpath +=
    attribute === "data-*"
      ? `[starts-with(@data-,'${value}')]`
      : `[contains(@${attribute},'${value}')]`;

  document.getElementById(inputId).value = xpath;
  document.getElementById(inputId).style.display = "block";
  document.querySelector(`#${inputId} + .structured-xpath-input`).remove();
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

export function setupSearch() {
  const searchInput = document.getElementById("search-input");
  const searchContainer = document.getElementById("search-container");
  const groupDropdown = document.getElementById("group-dropdown");
  const cameraRows = document.querySelectorAll(".camera-row");
  const filterColumn = document.getElementById("filter-column");
  const filterValue = document.getElementById("filter-value");
  const applyFilter = document.getElementById("apply-filter");
  const templateList = document.getElementById("template-list");
  const cameraTable = document.getElementById("camera-table");
  if (!searchInput) return;

  if (searchContainer) {
    searchContainer.style.display = "none";
    let fadeTimeout;
    const showSearch = () => {
      searchContainer.classList.remove("fade-out");
      clearTimeout(fadeTimeout);
      fadeTimeout = setTimeout(
        () => searchContainer.classList.add("fade-out"),
        3000,
      );
    };
    ["mousemove", "scroll"].forEach((evt) => {
      document.addEventListener(evt, showSearch);
    });
    window.addEventListener("templatesLoaded", (e) => {
      const count = e.detail?.count ?? 0;
      searchContainer.style.display = count > 10 ? "block" : "none";
      if (count > 10) showSearch();
    });
  }

  const filterCameras = () => {
    const costStart = document.getElementById("cost-start");
    const costEnd = document.getElementById("cost-end");
    if (costStart?.value || costEnd?.value) {
      const params = new URLSearchParams(window.location.search);
      if (costStart && costStart.value)
        params.set("cost_start", costStart.value);
      else params.delete("cost_start");
      if (costEnd && costEnd.value) params.set("cost_end", costEnd.value);
      else params.delete("cost_end");
      window.location.search = params.toString();
      return;
    }
    const searchTerm = searchInput.value.toLowerCase();
    const selectedGroup = groupDropdown
      ? groupDropdown.value
      : getSelectedGroup();
    const column = filterColumn ? filterColumn.value : "";
    const filterVal = filterValue ? filterValue.value.trim().toLowerCase() : "";
    cameraRows.forEach((row) => {
      const name = row
        .querySelector("td:first-child")
        .textContent.toLowerCase();
      const groups = row.dataset.groups.split(",");
      const rowText = row.textContent.toLowerCase();
      const matchesSearch = rowText.includes(searchTerm);
      const matchesGroup =
        selectedGroup === "all" || groups.includes(selectedGroup);
      let matchesKpi = true;
      if (column && filterVal) {
        const dataVal = row.dataset[column];
        if (dataVal) {
          const numericData = parseFloat(dataVal);
          const numericFilter = parseFloat(filterVal);
          if (!Number.isNaN(numericData) && !Number.isNaN(numericFilter)) {
            matchesKpi = numericData >= numericFilter;
          } else {
            matchesKpi = dataVal.toLowerCase().includes(filterVal);
          }
        }
      }
      row.style.display =
        matchesSearch && matchesGroup && matchesKpi ? "" : "none";
    });
  };

  const isCameraTable = cameraRows.length > 0;

  if (templateList && !isCameraTable) {
    const debouncedLoad = debounce(loadTemplates, 300);
    searchInput.addEventListener("input", debouncedLoad);
    if (groupDropdown) groupDropdown.addEventListener("change", debouncedLoad);
  } else {
    searchInput.addEventListener("input", filterCameras);
    if (groupDropdown) groupDropdown.addEventListener("change", filterCameras);
    if (filterColumn) filterColumn.addEventListener("change", filterCameras);
    if (filterValue) filterValue.addEventListener("input", filterCameras);
    if (applyFilter) applyFilter.addEventListener("click", filterCameras);
  }
}

export function templateMatchesSearch(template, searchQuery) {
  if (!searchQuery) return true;
  const name = template.name.toLowerCase();
  const groups = template.groups ? template.groups.toLowerCase() : "";
  return name.includes(searchQuery) || groups.includes(searchQuery);
}

export function virtualizeElements(container, elements, batch = 20) {
  if (!container) return;
  let index = 0;
  const sentinel = document.createElement("div");
  sentinel.className = "scroll-sentinel";
  container.appendChild(sentinel);

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) renderBatch();
    });
  });

  function renderBatch() {
    const slice = elements.slice(index, index + batch);
    slice.forEach((el) => container.insertBefore(el, sentinel));
    index += slice.length;
    if (index >= elements.length) {
      observer.disconnect();
      sentinel.remove();
    }
  }

  observer.observe(sentinel);
  renderBatch();
}

export async function loadTemplates() {
  const searchInput = document.getElementById("search-input");
  const selectedGroup = getSelectedGroup();
  const searchQuery = searchInput ? searchInput.value.toLowerCase() : "";
  const url = `/templates?group=${selectedGroup}&search=${searchQuery}&t=${new Date().getTime()}`;

  const slider = document.getElementById("grid-width-slider");

  updateGridLayout();

  const templateList = document.getElementById("template-list");
  const captionsTable = document.getElementById("captions-table");
  const templateContainer = document.querySelector(".template-container");
  const templateDetails = document
    .getElementById("template-form")
    ?.closest("details");

  const isIndexPage = Boolean(templateList);
  const isCaptionsPage = Boolean(captionsTable && templateContainer);
  const sliderElement = document.getElementById("grid-width-slider");

  if (isIndexPage) {
    templateList.innerHTML = '<div class="loading">Loading templates...</div>';
  } else if (isCaptionsPage) {
    templateContainer.innerHTML =
      '<div class="loading">Loading templates...</div>';
  }

  try {
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("Network response was not ok");
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const message =
        '<div class="error">Session expired. Please log in again.</div>';
      if (isIndexPage) {
        templateList.innerHTML = message;
      } else if (isCaptionsPage) {
        templateContainer.innerHTML = message;
      }
      return;
    }

    const templates = await response.json();

    if (isIndexPage) {
      templateList.innerHTML = "";
    } else if (isCaptionsPage) {
      templateContainer.innerHTML = "";
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const video = entry.target;
          if (entry.isIntersecting) {
            if (!video.poster && video.dataset.poster) {
              video.poster = video.dataset.poster;
            }
            if (isMobile()) {
              safePlay(video);
            }
          } else {
            video.pause();
          }
        });
      },
      { threshold: 0.5 },
    );

    let hasTemplates = false;
    let templateCount = 0;
    let firstTemplateName = null;
    const cards = [];
    Object.entries(templates).forEach(([name, template], index) => {
      if (
        templateBelongsToGroup(template, selectedGroup) &&
        templateMatchesSearch(template, searchQuery)
      ) {
        hasTemplates = true;
        templateCount += 1;
        if (!firstTemplateName) firstTemplateName = name;
        const lastScreenshotTime =
          template.last_screenshot_time || NO_TIMESTAMP_PLACEHOLDER;
        const humanizedTimestamp =
          lastScreenshotTime === NO_TIMESTAMP_PLACEHOLDER
            ? NO_TIMESTAMP_PLACEHOLDER
            : timeAgo(lastScreenshotTime);
        const nextCaptureTime = timeAgo(template.next_screenshot_time);

        const lastScreenshotDate = new Date(lastScreenshotTime);
        const ageMinutes = (Date.now() - lastScreenshotDate.getTime()) / 60000;
        const videoContainerClass = "video-container";
        const errorClass = template.capture_failed
          ? "template-error"
          : "recent-screenshot";
        const borderColor = computeBorderColor(
          ageMinutes,
          template.capture_failed,
        );

        if (isIndexPage) {
          const mobileView = isMobile();
          const templateDiv = createTemplateCard(
            name,
            template,
            index,
            mobileView,
          );

          void templateDiv.offsetWidth;
          setTimeout(() => {
            templateDiv.style.opacity = "1";
            templateDiv.style.transform = "translateY(0)";
          }, index * 100);

          const video = templateDiv.querySelector("video");
          observer.observe(video);
          attachVideoHover(video, name);
          cards.push(templateDiv);
        } else if (isCaptionsPage) {
          const templateDiv = document.createElement("div");
          templateDiv.classList.add("templateDiv");
          templateDiv.innerHTML = `
            <img src="/last_screenshot/${name}" alt="${name}" style="width:100%" title="${template.last_caption} (${humanizedTimestamp})">
            <div class="camera-name">${name}</div>
            <div class="timestamp" title="${
              lastScreenshotTime === NO_TIMESTAMP_PLACEHOLDER
                ? ""
                : formatExactTime(lastScreenshotTime)
            }">Last: ${humanizedTimestamp}</div>
            <div class="next-capture">Next: ${nextCaptureTime}</div>
            <textarea class="notes-textarea" id="notes-${name}" name="notes">${template.notes}</textarea>
            <button class="update-button" type="button" onclick="updateTemplate('${name}')">Update</button>
          `;
          templateContainer.appendChild(templateDiv);
        }
      }
    });

    if (isIndexPage && cards.length) {
      virtualizeElements(templateList, cards);
    }

    if (!hasTemplates) {
      const msg = document.createElement("div");
      msg.className = "no-templates";
      msg.textContent =
        'No templates found. Use "Add Camera" from the Settings → Discover tab to create one.';
      if (isIndexPage) {
        templateList.appendChild(msg);
      } else if (isCaptionsPage) {
        templateContainer.appendChild(msg);
      }
      if (templateDetails) templateDetails.open = true;
    }

    if (isIndexPage) {
      window.addEventListener("resize", updateGridLayout);
    }
    if (window.updateSliderLimits) {
      window.updateSliderLimits();
      if (slider) {
        slider.value = slider.min;
        slider.dispatchEvent(new Event("input"));
      }
    } else {
      if (slider) slider.dispatchEvent(new Event("input"));
    }
    if (
      isIndexPage &&
      searchQuery &&
      templateCount === 1 &&
      firstTemplateName
    ) {
      window.location.href = `/templates/${encodeURIComponent(
        firstTemplateName,
      )}`;
      return;
    }

    updateHumanizedTimes();
    window.dispatchEvent(
      new CustomEvent("templatesLoaded", { detail: { count: templateCount } }),
    );
    updateStatusCounts();
    applyStatusFilter();
    applyCaptionVisibility(parseFloat(sliderElement?.value || "0"));
    updateTableLayout(parseFloat(sliderElement?.value || "0"));
  } catch (error) {
    console.error("Error loading templates:", error);
    const errorMsg =
      '<div class="error">Error loading templates. Please try again.</div>';
    if (isIndexPage) {
      templateList.innerHTML = errorMsg;
    } else if (isCaptionsPage) {
      templateContainer.innerHTML = errorMsg;
    }
  }
}

export function setupTableSorting(tableId) {
  const headers = document.querySelectorAll(`#${tableId} th.sortable`);
  headers.forEach((th, index) => {
    th.addEventListener("click", () => {
      const type = th.dataset.type || "string";
      const tbody = th.closest("table").tBodies[0];
      const rows = Array.from(tbody.rows);
      const current = th.dataset.order === "asc" ? "asc" : "desc";
      rows.sort((a, b) => {
        const aVal = a.cells[index].dataset.value || a.cells[index].textContent;
        const bVal = b.cells[index].dataset.value || b.cells[index].textContent;
        if (type === "number") {
          return parseFloat(aVal) - parseFloat(bVal);
        }
        if (type === "date") {
          return new Date(aVal) - new Date(bVal);
        }
        return aVal.localeCompare(bVal);
      });
      if (current === "asc") {
        rows.reverse();
        th.dataset.order = "desc";
      } else {
        th.dataset.order = "asc";
      }
      rows.forEach((row) => tbody.appendChild(row));
    });
  });
}

export function setupSorting() {
  setupTableSorting("camera-table");
  setupTableSorting("feed-status");
  setupTableSorting("captions-table");
}

export function setupSortMenu() {
  const menu = document.getElementById("sort-date");
  if (!menu) return;
  menu.addEventListener("change", () => sortTemplates(menu.value));
}

export function sortTemplates(option) {
  const table = document.getElementById("camera-table");
  const list = document.getElementById("template-list");
  const [field, direction] = option.split("_");

  if (table) {
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows);
    const getVal = (row) => {
      if (field === "alpha") return row.textContent.trim().toLowerCase();
      if (field === "error") return parseInt(row.dataset.error || "0");
      return row.dataset[field] || "";
    };
    rows.sort((a, b) => {
      if (!field) {
        return parseInt(a.dataset.index) - parseInt(b.dataset.index);
      }
      if (field === "alpha") {
        return getVal(a).localeCompare(getVal(b));
      }
      if (field === "error") {
        return getVal(a) - getVal(b);
      }
      return new Date(getVal(a)) - new Date(getVal(b));
    });
    if (direction === "desc") rows.reverse();
    rows.forEach((row) => tbody.appendChild(row));
    return;
  }

  if (!list) return;
  const items = Array.from(list.querySelectorAll(".templateDiv"));
  const getVal = (item) => {
    if (field === "alpha") return item.dataset.name?.toLowerCase() || "";
    if (field === "error") return parseInt(item.dataset.error || "0");
    return item.dataset[field] || "";
  };
  items.sort((a, b) => {
    if (!field) {
      return parseInt(a.dataset.index) - parseInt(b.dataset.index);
    }
    if (field === "alpha") {
      return getVal(a).localeCompare(getVal(b));
    }
    if (field === "error") {
      return getVal(a) - getVal(b);
    }
    return new Date(getVal(a)) - new Date(getVal(b));
  });
  if (direction === "desc") items.reverse();
  items.forEach((item) => list.appendChild(item));
}

export function setupCaptionsFilter() {
  const searchInput = document.getElementById("captions-search");
  const rangeInput = document.getElementById("caption-range");
  const rangeLabel = document.getElementById("caption-range-label");
  const clearBtn = document.getElementById("caption-clear");
  const rows = document.querySelectorAll("#captions-table tbody tr");

  if (!searchInput || rows.length === 0) return;

  const parseDate = (str) => {
    if (!str) return null;
    const iso = str.includes("T") ? str : str.replace(" ", "T") + "Z";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  };

  // Escape user search term for safe use in RegExp
  const escapeRegExp = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Highlight occurrences of the search term within the caption cell
  const highlight = (cell, term) => {
    if (!cell) return;
    const raw = cell.dataset.raw || cell.textContent;
    cell.dataset.raw = raw;
    if (!term) {
      cell.innerHTML = raw;
      return;
    }
    const regex = new RegExp(`(${escapeRegExp(term)})`, "gi");
    cell.innerHTML = raw.replace(regex, "<mark>$1</mark>");
  };

  const filter = () => {
    const term = searchInput.value.toLowerCase().trim();
    const days = rangeInput ? parseInt(rangeInput.value, 10) : NaN;
    const start = Number.isFinite(days)
      ? new Date(Date.now() - days * 86400000)
      : null;

    rows.forEach((row) => {
      const timeElem = row.querySelector("td:first-child span");
      const rowDate = timeElem ? parseDate(timeElem.dataset.time) : null;
      const text = row.textContent.toLowerCase();
      let show = true;
      if (term && !text.includes(term)) show = false;
      if (start && rowDate && rowDate < start) show = false;
      row.style.display = show ? "" : "none";
      const captionCell = row.querySelector("td:nth-child(2)");
      if (show) highlight(captionCell, term);
      else if (captionCell)
        captionCell.innerHTML =
          captionCell.dataset.raw || captionCell.textContent;
    });
  };

  searchInput.addEventListener("input", filter);
  if (rangeInput) {
    rangeInput.addEventListener("input", () => {
      if (rangeLabel) rangeLabel.textContent = `Last ${rangeInput.value} days`;
    });
    rangeInput.addEventListener("change", filter);
  }
  if (clearBtn)
    clearBtn.addEventListener("click", () => {
      searchInput.value = "";
      if (rangeInput) rangeInput.value = "7";
      filter();
    });
}

let activeStatus = null;

export function applyStatusFilter() {
  document
    .querySelectorAll("#template-list .video-container")
    .forEach((box) => {
      const wrapper = box.closest(".templateDiv");
      if (!wrapper) return;
      const isRecent = box.classList.contains("recent-screenshot");
      const isError = box.classList.contains("template-error");
      let show = true;
      if (activeStatus === "recent") show = isRecent;
      else if (activeStatus === "error") show = isError;
      wrapper.style.display = show ? "" : "none";
    });
}

export function updateStatusCounts() {
  const legend = document.getElementById("status-legend");
  if (!legend) return;
  const recent = document.querySelectorAll(
    "#template-list .video-container.recent-screenshot",
  ).length;
  const error = document.querySelectorAll(
    "#template-list .video-container.template-error",
  ).length;
  legend
    .querySelector('[data-status="recent"]')
    ?.classList.toggle("disabled", recent === 0);
  legend
    .querySelector('[data-status="error"]')
    ?.classList.toggle("disabled", error === 0);
}

export function setupStatusFilter() {
  document.addEventListener("DOMContentLoaded", () => {
    const legend = document.getElementById("status-legend");
    if (!legend) return;
    legend.querySelectorAll(".status-item").forEach((item) => {
      item.dataset.status ||= item.textContent.trim().toLowerCase();
      item.addEventListener("click", () => {
        if (item.classList.contains("disabled")) return;
        const status = item.dataset.status;
        if (activeStatus === status) {
          activeStatus = null;
          item.classList.remove("active");
        } else {
          activeStatus = status;
          legend
            .querySelectorAll(".status-item")
            .forEach((i) => i.classList.toggle("active", i === item));
        }
        applyStatusFilter();
      });
    });
    updateStatusCounts();
    window.addEventListener("templatesLoaded", updateStatusCounts);
  });
}

export function updateBrowserOptions() {
  const browser = document.getElementById("browser");
  const headless = document.getElementById("headless");
  const stealth = document.getElementById("stealth");
  const popup = document.getElementById("popup_xpath");
  const dedicated = document.getElementById("dedicated_xpath");
  const enabled = browser && browser.checked;
  if (headless) {
    headless.disabled = !enabled;
    if (!enabled) headless.checked = false;
  }
  if (stealth) {
    stealth.disabled = !enabled;
    if (!enabled) stealth.checked = false;
  }
  if (popup) popup.disabled = !enabled;
  if (dedicated) dedicated.disabled = !enabled;
}

export function setupBrowserOptions() {
  document.addEventListener("DOMContentLoaded", () => {
    const browser = document.getElementById("browser");
    const popup = document.getElementById("popup_xpath");
    const dedicated = document.getElementById("dedicated_xpath");
    browser?.addEventListener("change", updateBrowserOptions);
    const ensureBrowser = () => {
      if (browser && !browser.checked) browser.checked = true;
      updateBrowserOptions();
    };
    popup?.addEventListener("input", ensureBrowser);
    dedicated?.addEventListener("input", ensureBrowser);
    updateBrowserOptions();
  });
}

export function confirmDeleteCamera(name) {
  const modal = document.getElementById("delete-camera-modal");
  const msg = document.getElementById("delete-camera-modal-message");
  const confirmBtn = document.getElementById("delete-camera-confirm");
  const cancelBtn = document.getElementById("delete-camera-cancel");
  const closeBtn = document.getElementById("delete-camera-close");
  if (!modal || !msg || !confirmBtn) return;
  msg.textContent = `Delete camera ${name}?`;
  modal.style.display = "block";
  const hide = () => {
    modal.style.display = "none";
  };
  const onConfirm = () => {
    hide();
    fetch("/templates", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    })
      .then((resp) => resp.json())
      .then(() => {
        document.querySelector(`.templateDiv[data-name='${name}']`)?.remove();
      })
      .catch((err) => console.error("Error:", err));
  };
  confirmBtn.addEventListener("click", onConfirm, { once: true });
  cancelBtn?.addEventListener("click", hide, { once: true });
  closeBtn?.addEventListener("click", hide, { once: true });
}

window.confirmDeleteCamera = confirmDeleteCamera;
