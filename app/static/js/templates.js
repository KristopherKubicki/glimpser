export function initTemplates() {
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('#template-form form');
    const groupDropdown = document.getElementById('group-dropdown');
    const groupsInput = document.getElementById('groups');
    const templateDetails = document
      .getElementById('template-form')?.closest('details');
    const slider = document.getElementById('grid-width-slider');
    const templateList = document.getElementById('template-list');

    if (slider) {
      const updateSliderLimits = () => {
        slider.max = window.innerWidth;
        const templateCount =
          templateList?.querySelectorAll('.templateDiv').length || 1;
        const computedMin = Math.max(
          50,
          Math.min(slider.max, Math.ceil(window.innerWidth / templateCount)),
        );
        slider.min = computedMin;
        if (parseFloat(slider.value) < computedMin) {
          slider.value = computedMin;
          if (templateList) {
            templateList.style.setProperty('--grid-item-width', `${computedMin}px`);
          }
        }
      };

      updateSliderLimits();
      window.addEventListener('resize', updateSliderLimits);
      window.updateSliderLimits = updateSliderLimits;
    }

    function autofillGroup() {
      if (groupsInput && groupDropdown && groupDropdown.value !== 'all') {
        groupsInput.value = groupDropdown.value;
      }
    }

    if (groupDropdown) {
      groupDropdown.addEventListener('change', () => {
        loadTemplates();
        if (templateDetails && templateDetails.open) {
          autofillGroup();
        }
      });
    }

    if (templateDetails) {
      templateDetails.addEventListener('toggle', () => {
        if (templateDetails.open) {
          autofillGroup();
        }
      });
    }

    if (slider && templateList) {
      slider.addEventListener('input', () => {
        const value = slider.value;
        templateList.style.setProperty('--grid-item-width', `${value}px`);

        const cameraNameFontSize = Math.max(10, Math.min(14, value / 25));
        const timestampFontSize = Math.max(8, Math.min(12, value / 30));
        document.documentElement.style.setProperty('--camera-name-font-size', `${cameraNameFontSize}px`);
        document.documentElement.style.setProperty('--timestamp-font-size', `${timestampFontSize}px`);
      });
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        const submitButton = form.querySelector('input[type="submit"]');
        const feedbackElement = document.createElement('div');
        feedbackElement.className = 'form-feedback';
        form.appendChild(feedbackElement);

        submitButton.disabled = true;
        submitButton.innerHTML = 'Submitting...';
        feedbackElement.textContent = 'Submitting form...';

        try {
          const response = await fetch('/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          });
          await response.json();
          loadTemplates();
          form.reset();

          feedbackElement.textContent = 'Source successfully created!';
          feedbackElement.style.color = 'green';
        } catch (error) {
          console.error('Error:', error);
          feedbackElement.textContent = 'An error occurred. Please try again.';
          feedbackElement.style.color = 'red';
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = 'Submit';
          setTimeout(() => feedbackElement.remove(), 3000);
        }
      });
    }

    loadGroups();
    loadTemplates();
    setupSearch();
    setupSorting();
    updateHumanizedTimes();
    setInterval(updateHumanizedTimes, 60000);
  });

  window.showStructuredInput = showStructuredInput;
  window.generateXPath = generateXPath;
}

export async function loadGroups() {
  const groupDropdown = document.getElementById('group-dropdown');
  if (!groupDropdown) return;
  groupDropdown.innerHTML = '<option value="all">Loading groups...</option>';
  groupDropdown.disabled = true;

  try {
    const response = await fetch('/groups');
    const groups = await response.json();
    groupDropdown.innerHTML = '<option value="all">All Groups</option>';
    groups.forEach((group) => {
      const option = document.createElement('option');
      option.value = group;
      option.textContent = group;
      groupDropdown.appendChild(option);
    });
  } catch (error) {
    console.error('Error loading groups:', error);
    groupDropdown.innerHTML = '<option value="all">Error loading groups</option>';
  } finally {
    groupDropdown.disabled = false;
  }
}

export function timeAgo(utcDateString) {
  const now = new Date();
  const utcDate = new Date(utcDateString);
  const diffInSeconds = Math.floor((now - utcDate) / 1000);
  if (diffInSeconds < 0) return 'in the future';

  const intervals = [
    { label: 'year', seconds: 31536000 },
    { label: 'month', seconds: 2592000 },
    { label: 'day', seconds: 86400 },
    { label: 'hour', seconds: 3600 },
    { label: 'minute', seconds: 60 },
    { label: 'second', seconds: 1 },
  ];

  for (const { label, seconds } of intervals) {
    const count = Math.floor(diffInSeconds / seconds);
    if (count >= 1) return `${count} ${label}${count > 1 ? 's' : ''} ago`;
  }
  return 'just now';
}

export function formatExactTime(utcDateString) {
  const date = new Date(utcDateString);
  return `UTC: ${date.toUTCString()}\nLocal: ${date.toString()}`;
}

export function isMobile() {
  return window.matchMedia('(hover: none)').matches;
}

export function updateGridLayout() {
  const templateList = document.getElementById('template-list');
  if (!templateList) return;
  if (isMobile()) {
    templateList.style.gridTemplateColumns = '1fr';
  } else {
    templateList.style.gridTemplateColumns = 'repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))';
  }
}

export function templateBelongsToGroup(template, group) {
  if (group === 'all') return true;
  const templateGroups = template.groups ? template.groups.split(',') : [];
  return templateGroups.includes(group);
}

export function updateHumanizedTimes() {
  document.querySelectorAll('.humanized-time').forEach((element) => {
    const timestamp = element.getAttribute('data-time');
    if (timestamp) {
      element.textContent = timeAgo(timestamp);
      element.title = formatExactTime(timestamp);
    }
  });

  document
    .querySelectorAll(
      '.video-container[data-timestamp], .templateDiv img[data-timestamp], video.hover-video[data-timestamp]'
    )
    .forEach((element) => {
      const original =
        element.dataset.originalTimestamp || element.getAttribute('data-timestamp');
      if (!element.dataset.originalTimestamp) {
        element.dataset.originalTimestamp = original;
      }
      if (original) {
        element.setAttribute('data-timestamp', timeAgo(original));
        element.setAttribute('title', formatExactTime(original));
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
  input.insertAdjacentHTML('afterend', structuredInputHtml);
  input.style.display = 'none';
}

export function generateXPath(inputId) {
  const tag = document.getElementById(`${inputId}_tag`).value;
  const attribute = document.getElementById(`${inputId}_attribute`).value;
  const value = document.getElementById(`${inputId}_value`).value;

  let xpath = `//${tag}`;
  xpath += attribute === 'data-*'
    ? `[starts-with(@data-,'${value}')]`
    : `[contains(@${attribute},'${value}')]`;

  document.getElementById(inputId).value = xpath;
  document.getElementById(inputId).style.display = 'block';
  document.querySelector(`#${inputId} + .structured-xpath-input`).remove();
}

export function setupSearch() {
  const searchInput = document.getElementById('search-input');
  const groupDropdown = document.getElementById('group-dropdown');
  const cameraRows = document.querySelectorAll('.camera-row');
  const filterColumn = document.getElementById('filter-column');
  const filterValue = document.getElementById('filter-value');
  const applyFilter = document.getElementById('apply-filter');
  const templateList = document.getElementById('template-list');
  if (!searchInput || !groupDropdown) return;

  const filterCameras = () => {
    const searchTerm = searchInput.value.toLowerCase();
    const selectedGroup = groupDropdown.value;
    const column = filterColumn ? filterColumn.value : '';
    const filterVal = filterValue ? filterValue.value.trim().toLowerCase() : '';
    cameraRows.forEach((row) => {
      const name = row.querySelector('td:first-child').textContent.toLowerCase();
      const groups = row.dataset.groups.split(',');
      const rowText = row.textContent.toLowerCase();
      const matchesSearch = rowText.includes(searchTerm);
      const matchesGroup = selectedGroup === 'all' || groups.includes(selectedGroup);
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
      row.style.display = matchesSearch && matchesGroup && matchesKpi ? '' : 'none';
    });
  };

  if (templateList) {
    searchInput.addEventListener('input', loadTemplates);
    groupDropdown.addEventListener('change', loadTemplates);
  } else {
    searchInput.addEventListener('input', filterCameras);
    groupDropdown.addEventListener('change', filterCameras);
    if (applyFilter) applyFilter.addEventListener('click', filterCameras);
  }
}

export function templateMatchesSearch(template, searchQuery) {
  if (!searchQuery) return true;
  const name = template.name.toLowerCase();
  const groups = template.groups ? template.groups.toLowerCase() : '';
  return name.includes(searchQuery) || groups.includes(searchQuery);
}

export async function loadTemplates() {
  const groupDropdown = document.getElementById('group-dropdown');
  const searchInput = document.getElementById('search-input');
  const selectedGroup = groupDropdown ? groupDropdown.value || 'all' : 'all';
  const searchQuery = searchInput ? searchInput.value.toLowerCase() : '';
  const url = `/templates?group=${selectedGroup}&search=${searchQuery}&t=${new Date().getTime()}`;

  updateGridLayout();

  const templateList = document.getElementById('template-list');
  const captionsTable = document.querySelector('details table');
  const templateContainer = document.querySelector('.template-container');

  const isIndexPage = Boolean(templateList);
  const isCaptionsPage = Boolean(captionsTable && templateContainer);

  if (isIndexPage) {
    templateList.innerHTML = '<div class="loading">Loading templates...</div>';
  } else if (isCaptionsPage) {
    templateContainer.innerHTML = '<div class="loading">Loading templates...</div>';
  }

  try {
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error('Network response was not ok');
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
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
      templateList.innerHTML = '';
    } else if (isCaptionsPage) {
      templateContainer.innerHTML = '';
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (isMobile() && entry.isIntersecting) {
          entry.target.play();
        } else {
          entry.target.pause();
        }
      });
    }, { threshold: 0.5 });

    let hasTemplates = false;
    Object.entries(templates).forEach(([name, template], index) => {
      if (
        templateBelongsToGroup(template, selectedGroup) &&
        templateMatchesSearch(template, searchQuery)
      ) {
        hasTemplates = true;
        const lastScreenshotTime = template.last_screenshot_time;
        const humanizedTimestamp = timeAgo(lastScreenshotTime);
        const nextCaptureTime = timeAgo(template.next_screenshot_time);

        const lastScreenshotDate = new Date(lastScreenshotTime);
        const oneMinuteAgo = new Date(Date.now() - 60000);
        const isRecent = lastScreenshotDate > oneMinuteAgo;
        const videoContainerClass = isRecent ? 'video-container recent-screenshot' : 'video-container';
        const errorClass = template.capture_failed ? 'template-error' : '';

        if (isIndexPage) {
          const templateDiv = document.createElement('div');
          templateDiv.classList.add('templateDiv');
          templateDiv.style.opacity = '0';
          templateDiv.style.transform = 'translateY(20px)';
          templateDiv.style.transition = 'opacity 0.5s ease, transform 0.5s ease';

          templateDiv.innerHTML = `
            <a href='/templates/${name}'>
              <div class="${videoContainerClass} ${errorClass}" data-timestamp="${lastScreenshotTime}">
                <div class="camera-name">${name}</div>
                <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" style="width:100%" muted title="${template.last_caption} (${humanizedTimestamp})" preload="none">
                  <source src="/last_video/${name}" type="video/mp4">
                  Your browser does not support the video tag.
                </video>
                <div class="play-icon">&#9658;</div>
              </div>
            </a>
            <a href='${template.url}' target='_blank' class='open-url-link' title='Open monitored page' aria-label='Open monitored page'>↗</a>
          `;
          templateList.appendChild(templateDiv);

          void templateDiv.offsetWidth;
          setTimeout(() => {
            templateDiv.style.opacity = '1';
            templateDiv.style.transform = 'translateY(0)';
          }, index * 100);

          const video = templateDiv.querySelector('video');
          observer.observe(video);

          video.addEventListener('mouseenter', () => {
            video.playbackRate = 2.0;
            video.play();
          });
          video.addEventListener('mouseleave', () => {
            video.playbackRate = 1.0;
            video.pause();
          });
        } else if (isCaptionsPage) {
          const templateDiv = document.createElement('div');
          templateDiv.classList.add('templateDiv');
          templateDiv.innerHTML = `
            <img src="/last_screenshot/${name}" alt="${name}" style="width:100%">
            <div class="camera-name">${name}</div>
            <div class="timestamp" title="${formatExactTime(lastScreenshotTime)}">Last: ${humanizedTimestamp}</div>
            <div class="next-capture">Next: ${nextCaptureTime}</div>
            <textarea class="notes-textarea" id="notes-${name}" name="notes">${template.notes}</textarea>
            <button class="update-button" type="button" onclick="updateTemplate('${name}')">Update</button>
          `;
          templateContainer.appendChild(templateDiv);
        }
      }
    });

    if (!hasTemplates) {
      const msg = document.createElement('div');
      msg.className = 'no-templates';
      msg.textContent = 'No templates found. Use "Add Template" above to create one.';
      if (isIndexPage) {
        templateList.appendChild(msg);
      } else if (isCaptionsPage) {
        templateContainer.appendChild(msg);
      }
      if (templateDetails) templateDetails.open = true;
    }

    if (isIndexPage) {
      window.addEventListener('resize', updateGridLayout);
      if (window.updateSliderLimits) window.updateSliderLimits();
    }
    if (isCaptionsPage) {
      updateHumanizedTimes();
    }
  } catch (error) {
    console.error('Error loading templates:', error);
    const errorMsg = '<div class="error">Error loading templates. Please try again.</div>';
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
    th.addEventListener('click', () => {
      const type = th.dataset.type || 'string';
      const tbody = th.closest('table').tBodies[0];
      const rows = Array.from(tbody.rows);
      const current = th.dataset.order === 'asc' ? 'asc' : 'desc';
      rows.sort((a, b) => {
        const aVal = a.cells[index].dataset.value || a.cells[index].textContent;
        const bVal = b.cells[index].dataset.value || b.cells[index].textContent;
        if (type === 'number') {
          return parseFloat(aVal) - parseFloat(bVal);
        }
        if (type === 'date') {
          return new Date(aVal) - new Date(bVal);
        }
        return aVal.localeCompare(bVal);
      });
      if (current === 'asc') {
        rows.reverse();
        th.dataset.order = 'desc';
      } else {
        th.dataset.order = 'asc';
      }
      rows.forEach((row) => tbody.appendChild(row));
    });
  });
}

export function setupSorting() {
  setupTableSorting('camera-table');
  setupTableSorting('feed-status');
}
