// app/static/js/script.js

document.addEventListener('DOMContentLoaded', () => {
  // Cache DOM elements
  const form = document.querySelector('#template-form form');
  const groupDropdown = document.getElementById('group-dropdown');
  const slider = document.getElementById('grid-width-slider');
  const templateList = document.getElementById('template-list');
  const searchInput = document.getElementById('search-input');

  // Setup event listeners
  if (groupDropdown) {
    groupDropdown.addEventListener('change', loadTemplates);
  }

  if (slider && templateList) {
    slider.addEventListener('input', () => {
      const value = slider.value;
      templateList.style.setProperty('--grid-item-width', `${value}px`);

      // Calculate font sizes based on the slider value
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

      // Show loading indicator
      submitButton.disabled = true;
      submitButton.innerHTML = 'Submitting...';
      feedbackElement.textContent = 'Submitting form...';

      try {
        const response = await fetch('/templates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const result = await response.json();
        console.log('Success:', result);
        loadTemplates();
        form.reset();

        // Show success message
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

  // Initial load
  loadGroups();
  loadTemplates();
  setupSearch();
  setupStatusPageVideoHover();
  setupVideoControls();

  // Play All / Stop All functionality for index page videos
  const playAllButton = document.getElementById('play-all-button');
  let isPlaying = false;
  if (playAllButton) {
    playAllButton.addEventListener('click', () => {
      const videos = document.querySelectorAll('.templateDiv video');
      if (isPlaying) {
        videos.forEach((video) => {
          video.pause();
          video.currentTime = 0;
        });
        playAllButton.textContent = 'Play All';
      } else {
        videos.forEach((video) => {
          video.play().catch((e) => console.error('Error playing video:', e));
        });
        playAllButton.textContent = 'Stop All';
      }
      isPlaying = !isPlaying;
    });
  }
  
  // Update video sources every 30 minutes
  setInterval(updateVideoSources, 60000 * 30);
});

// Helper functions

async function loadGroups() {
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

function timeAgo(utcDateString) {
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

function formatExactTime(utcDateString) {
  const date = new Date(utcDateString);
  return `UTC: ${date.toUTCString()}\nLocal: ${date.toString()}`;
}

function updateVideoSources() {
  const videos = document.querySelectorAll('.templateDiv video');
  videos.forEach((video) => {
    const name = video.getAttribute('data-name');
    const timestamp = new Date().getTime();
    video.querySelector('source').src = `/last_video/${name}?t=${timestamp}`;
    video.poster = `/last_screenshot/${name}?t=${timestamp}`;
    // Optionally reload video if needed: video.load();
  });
}

function isMobile() {
  return window.matchMedia('(hover: none)').matches;
}

function updateGridLayout() {
  const templateList = document.getElementById('template-list');
  if (!templateList) return;
  if (isMobile()) {
    templateList.style.gridTemplateColumns = '1fr';
  } else {
    templateList.style.gridTemplateColumns = 'repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))';
  }
}

function templateBelongsToGroup(template, group) {
  if (group === 'all') return true;
  const templateGroups = template.groups ? template.groups.split(',') : [];
  return templateGroups.includes(group);
}

function updateHumanizedTimes() {
  document.querySelectorAll('.humanized-time').forEach((element) => {
    const timestamp = element.getAttribute('data-time');
    if (timestamp) element.textContent = timeAgo(timestamp);
  });
}

function isInViewport(element) {
  const rect = element.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
  );
}

function showStructuredInput(inputId) {
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

function generateXPath(inputId) {
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

function setupSearch() {
  const searchInput = document.getElementById('search-input');
  const groupDropdown = document.getElementById('group-dropdown');
  const cameraRows = document.querySelectorAll('.camera-row');
  const templateList = document.getElementById('template-list');
  if (!searchInput || !groupDropdown) return;

  const filterCameras = () => {
    const searchTerm = searchInput.value.toLowerCase();
    const selectedGroup = groupDropdown.value;
    cameraRows.forEach((row) => {
      const name = row.querySelector('td:first-child').textContent.toLowerCase();
      const groups = row.dataset.groups.split(',');
      const matchesSearch = name.includes(searchTerm);
      const matchesGroup = selectedGroup === 'all' || groups.includes(selectedGroup);
      row.style.display = matchesSearch && matchesGroup ? '' : 'none';
    });
  };

  if (templateList) {
    searchInput.addEventListener('input', loadTemplates);
    groupDropdown.addEventListener('change', loadTemplates);
  } else {
    searchInput.addEventListener('input', filterCameras);
    groupDropdown.addEventListener('change', filterCameras);
  }
}

function templateMatchesSearch(template, searchQuery) {
  if (!searchQuery) return true;
  const name = template.name.toLowerCase();
  const groups = template.groups ? template.groups.toLowerCase() : '';
  return name.includes(searchQuery) || groups.includes(searchQuery);
}

async function loadTemplates() {
  const groupDropdown = document.getElementById('group-dropdown');
  const searchInput = document.getElementById('search-input');
  const selectedGroup = groupDropdown ? groupDropdown.value || 'all' : 'all';
  const searchQuery = searchInput ? searchInput.value.toLowerCase() : '';
  const url = `/templates?group=${selectedGroup}&search=${searchQuery}&t=${new Date().getTime()}`;

  updateGridLayout();

  // Determine page type
  const templateList = document.getElementById('template-list');
  const captionsTable = document.querySelector('details table');
  const templateContainer = document.querySelector('.template-container');

  const isIndexPage = Boolean(templateList);
  const isCaptionsPage = Boolean(captionsTable && templateContainer);

  // Show loading indicator
  if (isIndexPage) {
    templateList.innerHTML = '<div class="loading">Loading templates...</div>';
  } else if (isCaptionsPage) {
    templateContainer.innerHTML = '<div class="loading">Loading templates...</div>';
  }

  try {
    const response = await fetch(url);
    const templates = await response.json();

    if (isIndexPage) {
      templateList.innerHTML = '';
    } else if (isCaptionsPage) {
      templateContainer.innerHTML = '';
    }

    // Intersection observer for video autoplay on mobile
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (isMobile() && entry.isIntersecting) {
          entry.target.play();
        } else {
          entry.target.pause();
        }
      });
    }, { threshold: 0.5 });

    Object.entries(templates).forEach(([name, template], index) => {
      if (
        templateBelongsToGroup(template, selectedGroup) &&
        templateMatchesSearch(template, searchQuery)
      ) {
        const lastScreenshotTime = template.last_screenshot_time;
        const humanizedTimestamp = timeAgo(lastScreenshotTime);
        const nextCaptureTime = timeAgo(template.next_screenshot_time);

        // Determine if screenshot is recent (<1 minute)
        const lastScreenshotDate = new Date(lastScreenshotTime);
        const oneMinuteAgo = new Date(Date.now() - 60000);
        const isRecent = lastScreenshotDate > oneMinuteAgo;
        const videoContainerClass = isRecent ? "video-container recent-screenshot" : "video-container";

        if (isIndexPage) {
          const templateDiv = document.createElement('div');
          templateDiv.classList.add("templateDiv");
          templateDiv.style.opacity = '0';
          templateDiv.style.transform = 'translateY(20px)';
          templateDiv.style.transition = 'opacity 0.5s ease, transform 0.5s ease';

          templateDiv.innerHTML = `
            <a href='/templates/${name}'>
              <div class="${videoContainerClass}">
                <div class="camera-name">${name}</div>
                <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" style="width:100%" muted title="${template.last_caption} (${humanizedTimestamp})" preload="none">
                  <source src="/last_video/${name}" type="video/mp4">
                  Your browser does not support the video tag.
                </video>
                <div class="timestamp" title="${formatExactTime(lastScreenshotTime)}">${humanizedTimestamp}</div>
                <div class="play-icon">&#9658;</div>
              </div>
            </a>
          `;
          templateList.appendChild(templateDiv);

          // Trigger transition effect
          void templateDiv.offsetWidth;
          setTimeout(() => {
            templateDiv.style.opacity = '1';
            templateDiv.style.transform = 'translateY(0)';
          }, index * 100);

          const video = templateDiv.querySelector('video');
          observer.observe(video);

          // Fast playback on hover
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
          templateDiv.classList.add("templateDiv");
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

    if (isIndexPage) {
      window.addEventListener('resize', updateGridLayout);
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

// Video controls for live-video and cast functionality
function setupVideoControls() {
  const video = document.getElementById('live-video');
  if (!video) return;

  const playPauseButton = document.getElementById('play-pause');
  const muteButton = document.getElementById('mute');
  const fullScreenButton = document.getElementById('full-screen');
  const seekBar = document.getElementById('seek-bar');
  const volumeBar = document.getElementById('volume-bar');
  const castButton = document.getElementById('cast-button');

  if (playPauseButton) {
    playPauseButton.addEventListener('click', () => {
      video.paused ? video.play() : video.pause();
    });
  }
  if (muteButton) {
    muteButton.addEventListener('click', () => {
      video.muted = !video.muted;
    });
  }
  if (fullScreenButton) {
    fullScreenButton.addEventListener('click', () => {
      if (video.requestFullscreen) video.requestFullscreen();
      else if (video.mozRequestFullScreen) video.mozRequestFullScreen();
      else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
      else if (video.msRequestFullscreen) video.msRequestFullscreen();
    });
  }
  if (seekBar) {
    seekBar.addEventListener('change', () => {
      video.currentTime = video.duration * (seekBar.value / 100);
    });
    video.addEventListener('timeupdate', () => {
      seekBar.value = (100 / video.duration) * video.currentTime;
    });
  }
  if (volumeBar) {
    volumeBar.addEventListener('change', () => {
      video.volume = volumeBar.value;
    });
  }
  if (castButton) {
    castButton.addEventListener('click', startCasting);
  }
}

// Setup status page video hover functionality
function setupStatusPageVideoHover() {
  const thumbnailVideoCells = document.querySelectorAll('.thumbnail-video');
  thumbnailVideoCells.forEach(cell => {
    const img = cell.querySelector('img.thumbnail');
    const video = cell.querySelector('video.hover-video');
    if (img && video) {
      cell.addEventListener('mouseenter', () => {
        img.style.display = 'none';
        video.style.display = 'block';
        video.play();
      });
      cell.addEventListener('mouseleave', () => {
        video.pause();
        video.currentTime = 0;
        video.style.display = 'none';
        img.style.display = 'block';
      });
    }
  });
}

// Scheduler toggle functionality
const toggleSchedulerButton = document.getElementById('toggle-scheduler');
const schedulerStatus = document.getElementById('scheduler-status');
if (toggleSchedulerButton && schedulerStatus) {
  toggleSchedulerButton.addEventListener('click', () => {
    fetch('/toggle_scheduler', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        schedulerStatus.textContent = data.status;
        toggleSchedulerButton.textContent = data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
      })
      .catch(error => {
        console.error('Error:', error);
        schedulerStatus.textContent = 'Error occurred';
      });
  });

  // Check initial scheduler status
  fetch('/scheduler_status')
    .then(res => res.json())
    .then(data => {
      schedulerStatus.textContent = data.status;
      toggleSchedulerButton.textContent = data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
    })
    .catch(error => {
      console.error('Error:', error);
      schedulerStatus.textContent = 'Error occurred';
    });
}


// Google Cast API initialization
function initializeCastApi() {
  cast.framework.CastContext.getInstance().setOptions({
    receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
    autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
  });
}

window['__onGCastApiAvailable'] = function(isAvailable) {
  if (isAvailable) initializeCastApi();
};

function startCasting() {
  const castSession = cast.framework.CastContext.getInstance().getCurrentSession();
  if (castSession) {
    const mediaInfo = new chrome.cast.media.MediaInfo(
      document.getElementById('live-video').src,
      'video/mp4'
    );
    const request = new chrome.cast.media.LoadRequest(mediaInfo);
    castSession.loadMedia(request).then(
      () => console.log('Cast started'),
      errorCode => console.error('Error code: ' + errorCode)
    );
  } else {
    console.log('No active cast session');
  }
}

