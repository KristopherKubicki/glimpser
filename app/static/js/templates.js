import { enqueueClip } from "./video.js";
import {
  NO_TIMESTAMP_PLACEHOLDER,
  timeAgo,
  formatExactTime,
  updateHumanizedTimes,
} from "./time_utils.js";
import { loadGroups, getSelectedGroup } from "./group_utils.js";
import {
  createTemplateCard,
  setCaptionsVisibility,
  getCaptionsVisibility,
  applyCaptionVisibility,
  updateTableLayout,
  isMobile,
  computeBorderColor,
  setupTileResizeDrag,
  updateGridLayout,
} from "./grid_utils.js";
import {
  applyStatusFilter,
  updateStatusCounts,
  setupStatusFilter,
} from "./status_filter.js";

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
    const isGroupWall =
      typeof window !== "undefined" &&
      Boolean(window.currentGroup) &&
      window.currentGroup !== "all";

    if (slider) {
      // Auto-fit makes the templates view behave like a video wall (fill the viewport).
      // Default ON; moving the slider manually will turn it off.
      slider.dataset.autofit = localStorage.getItem("gridAutofit") || "1";
      if (isGroupWall) slider.dataset.autofit = "1";
      let sliderInitialized = false;
      let isProgrammaticSliderUpdate = false;
      const updateSliderLimits = () => {
        slider.max = Math.min(window.innerWidth, MAX_THUMBNAIL_WIDTH);
        if (isMobile) {
          slider.min = slider.max;
          slider.value = slider.max;
          if (isGroupWall && list) {
            // Wall layout: stretch tiles to fill the available width/height.
            list.dataset.wallLayout = "1";
            if (bestCols && Number.isFinite(bestCols)) {
              list.style.gridTemplateColumns = `repeat(${bestCols}, 1fr)`;
            }
          } else if (list) {
            list.dataset.wallLayout = "0";
            list.style.gridTemplateColumns = "";
          }
          document.documentElement.style.setProperty(
            "--tile-size",
            `${slider.value}px`,
          );
          slider.dispatchEvent(new Event("input"));
          return;
        }

        // When we're in a dedicated group view ("/templates/<group>"), prefer a
        // "video wall" fit: use the *visible* tile count and resize to fill the viewport.
        // The index view virtualizes tiles for performance; in that case use the
        // server-provided total count so sizing remains stable while scrolling.
        const list = templateList;
        const isVirtualized = list?.dataset.virtualized === "1";
        const allTiles = list
          ? Array.from(
              list.querySelectorAll(".templateDiv:not(.skeleton-card)"),
            )
          : [];
        const visibleTiles = allTiles.filter((el) => {
          if (el.style.display === "none") return false;
          return el.offsetParent !== null;
        });
        const totalTemplates =
          (isGroupWall
            ? visibleTiles.length || allTiles.length
            : isVirtualized
              ? Number(window.templatesTotalCount)
              : visibleTiles.length || allTiles.length) ||
          Number(window.templatesTotalCount) ||
          1;

        const gap = list
          ? parseFloat(getComputedStyle(list).gap || "0") || 0
          : 0;

        // Iterate over possible column counts to find the largest tile width
        // that fits the viewport horizontally and vertically.
        let bestWidth = 50;
        let bestCols = 1;
        // Prefer measuring the actual grid viewport instead of approximating via
        // window size - headers/footers/overlays differ per page.
        let availableWidth = window.innerWidth;
        let availableHeight = window.innerHeight;
        if (list) {
          const rect = list.getBoundingClientRect();
          if (rect.width > 0) availableWidth = rect.width;
          if (rect.height > 0) availableHeight = rect.height;
        }

        for (let cols = 1; cols <= totalTemplates; cols++) {
          const maxWidthForCols = Math.floor(
            (availableWidth - gap * (cols - 1)) / cols,
          );
          if (maxWidthForCols < 50) break;
          const rows = Math.ceil(totalTemplates / cols);
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
        const currentValue = parseFloat(slider.value || "0") || computedMin;
        const shouldInitializeToFit = !sliderInitialized;
        const shouldAutoFit = slider.dataset.autofit === "1" || isGroupWall;
        const clampedValue = Math.max(computedMin, currentValue);
        if (
          shouldAutoFit ||
          shouldInitializeToFit ||
          clampedValue !== currentValue
        ) {
          isProgrammaticSliderUpdate = true;
          slider.value = shouldAutoFit
            ? computedMin
            : shouldInitializeToFit
              ? computedMin
              : clampedValue;
          if (isGroupWall && list) {
            // Wall layout: stretch tiles to fill the available width/height.
            list.dataset.wallLayout = "1";
            if (bestCols && Number.isFinite(bestCols)) {
              list.style.gridTemplateColumns = `repeat(${bestCols}, 1fr)`;
            }
          } else if (list) {
            list.dataset.wallLayout = "0";
            list.style.gridTemplateColumns = "";
          }
          document.documentElement.style.setProperty(
            "--tile-size",
            `${slider.value}px`,
          );
          slider.dispatchEvent(new Event("input"));
          isProgrammaticSliderUpdate = false;
        }
        sliderInitialized = true;
      };

      updateSliderLimits();
      window.addEventListener("resize", updateSliderLimits);
      window.updateSliderLimits = updateSliderLimits;
      slider.dispatchEvent(new Event("input"));
    }

    if (captionToggle) {
      captionToggle.addEventListener("click", () => {
        if (captionToggle.classList.contains("disabled")) return;
        setCaptionsVisibility(!getCaptionsVisibility());
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

export function templateBelongsToGroup(template, group) {
  if (group === "all") return true;
  const templateGroups = template.groups ? template.groups.split(",") : [];
  return templateGroups.includes(group);
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
  const templateContainer =
    document.querySelector(".template-container") || templateList;
  const templateDetails = document
    .getElementById("template-form")
    ?.closest("details");

  const isIndexPage = Boolean(templateList);
  const isCaptionsPage = Boolean(captionsTable && templateContainer);
  const sliderElement = document.getElementById("grid-width-slider");

  const SKELETON_COUNT = 6;
  if (isIndexPage || isCaptionsPage) {
    const container = isIndexPage ? templateList : templateContainer;
    container.innerHTML = "";
    for (let i = 0; i < SKELETON_COUNT; i++) {
      const card = document.createElement("div");
      card.className = "templateDiv skeleton-card";
      if (isCaptionsPage) {
        const line = document.createElement("div");
        line.className = "skeleton-line";
        card.appendChild(line);
      }
      container.appendChild(card);
    }
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

    // Some pages virtualize tiles for performance, which means
    // `querySelectorAll(".templateDiv")` is not a reliable count.
    // Persist the real count so the slider can compute a correct "fit on one page" size.
    window.templatesTotalCount = templateCount;

    if (isIndexPage && cards.length) {
      const isGroupWall =
        typeof window !== "undefined" &&
        Boolean(window.currentGroup) &&
        window.currentGroup !== "all";
      const slider = document.getElementById("grid-width-slider");
      const shouldVirtualize =
        !isGroupWall &&
        cards.length > 60 &&
        !(slider && slider.dataset.autofit === "1");
      if (shouldVirtualize) {
        templateList.dataset.virtualized = "1";
        virtualizeElements(templateList, cards);
      } else {
        templateList.dataset.virtualized = "0";
        cards.forEach((el) => templateList.appendChild(el));
      }
    } else if (isIndexPage) {
      templateList.dataset.virtualized = "0";
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
      if (slider && slider.dataset.autofit === "1") {
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
  setupTableSorting("top-failures");
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

export {
  createTemplateCard,
  setCaptionsVisibility,
  getCaptionsVisibility,
  applyCaptionVisibility,
  updateTableLayout,
  isMobile,
  computeBorderColor,
  setupTileResizeDrag,
  updateGridLayout,
  loadGroups,
  getSelectedGroup,
  NO_TIMESTAMP_PLACEHOLDER,
  timeAgo,
  formatExactTime,
  updateHumanizedTimes,
  applyStatusFilter,
  updateStatusCounts,
  setupStatusFilter,
};
