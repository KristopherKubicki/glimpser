// app/static/js/script.js

document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('#template-form form');

    const groupDropdown = document.getElementById('group-dropdown');
    if (groupDropdown)  {
    groupDropdown.addEventListener('change', () => {
        loadTemplates(); // Reload templates based on the selected group
    });
	}

    const slider = document.getElementById('grid-width-slider');
    const templateList = document.getElementById('template-list');

	if (slider) {
    slider.addEventListener('input', function () {
        const value = slider.value;
        const pxValue = value + 'px';
        templateList.style.setProperty('--grid-item-width', pxValue);

        // Calculate font sizes based on the slider value
        const cameraNameFontSize = Math.max(10, Math.min(14, value / 25)); // Min 10px, Max 14px
        const timestampFontSize = Math.max(8, Math.min(12, value / 30)); // Min 8px, Max 12px

        // Update CSS variables
        document.documentElement.style.setProperty('--camera-name-font-size', `${cameraNameFontSize}px`);
        document.documentElement.style.setProperty('--timestamp-font-size', `${timestampFontSize}px`);
    });
	}

	if (form) {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        const submitButton = form.querySelector('input[type="submit"]');
	    console.log(submitButton);
        const feedbackElement = document.createElement('div');
        feedbackElement.className = 'form-feedback';
        form.appendChild(feedbackElement);

        // Show loading indicator
        submitButton.disabled = true;
        submitButton.innerHTML = 'Submitting...';
        feedbackElement.innerHTML = 'Submitting form...';

        fetch('/templates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
            loadTemplates(); // Refresh the list after submission
            form.reset(); // Reset form after successful submission

            // Show success message
            feedbackElement.innerHTML = 'Source successfully created!';
            feedbackElement.style.color = 'green';
        })
        .catch((error) => {
            console.error('Error:', error);

            // Show error message
            feedbackElement.innerHTML = 'An error occurred. Please try again.';
            feedbackElement.style.color = 'red';
        })
        .finally(() => {
            // Reset button state
            submitButton.disabled = false;
            submitButton.innerHTML = 'Submit';

            // Remove feedback message after 3 seconds
            setTimeout(() => {
                feedbackElement.remove();
            }, 3000);
        });
    });
    }

function loadGroups() {
    const groupDropdown = document.getElementById('group-dropdown');
    groupDropdown.innerHTML = '<option value="all">Loading groups...</option>';
    groupDropdown.disabled = true;

    fetch('/groups')
        .then(response => response.json())
        .then(groups => {
            groupDropdown.innerHTML = '<option value="all">All Groups</option>';
            groups.forEach(group => {
                const option = document.createElement('option');
                option.value = group;
                option.textContent = group;
                groupDropdown.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading groups:', error);
            groupDropdown.innerHTML = '<option value="all">Error loading groups</option>';
        })
        .finally(() => {
            groupDropdown.disabled = false;
        });
}


function timeAgo(utcDateString) {
    const now = new Date();
    const utcDate = new Date(utcDateString);
    const diffInSeconds = Math.floor((now - utcDate) / 1000);

    if (diffInSeconds < 0) {
        return 'in the future';
    }

    const intervals = [
        { label: 'year', seconds: 31536000 },
        { label: 'month', seconds: 2592000 },
        { label: 'day', seconds: 86400 },
        { label: 'hour', seconds: 3600 },
        { label: 'minute', seconds: 60 },
        { label: 'second', seconds: 1 }
    ];

    for (let i = 0; i < intervals.length; i++) {
        const interval = intervals[i];
        const count = Math.floor(diffInSeconds / interval.seconds);
        if (count >= 1) {
            return `${count} ${interval.label}${count > 1 ? 's' : ''} ago`;
        }
    }

    return 'just now';
}

function formatExactTime(utcDateString) {
    const date = new Date(utcDateString);
    const utcString = date.toUTCString();
    const localString = date.toString();
    return `UTC: ${utcString}\nLocal: ${localString}`;
}

function updateVideoSources() {
    const videos = document.querySelectorAll('.templateDiv video');
    videos.forEach(video => {
        // Update the video source and poster
        const name = video.getAttribute('data-name'); // Assuming you set a data-name attribute to store the template name
        const newSource = `/last_video/${name}?t=${new Date().getTime()}`; // Prevent caching with a unique timestamp query parameter
        const newPoster = `/last_screenshot/${name}?t=${new Date().getTime()}`; // Same for the poster

        // Update the source
        const source = video.querySelector('source');
        source.src = newSource;

        // Update the poster
        video.poster = newPoster;

        // Load the new video
        ///video.load();
    });
}

function isMobile() {
    return window.matchMedia("(hover: none)").matches;
}

function updateGridLayout() {
    const templateList = document.getElementById('template-list');
    if (isMobile()) {
        templateList.style.gridTemplateColumns = '1fr'; // Set to single column layout
    } else if (templateList) {
        templateList.style.gridTemplateColumns = 'repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))'; // Set to dynamic column layout
    }
}

function templateBelongsToGroup(template, group) {
    console.log(group);
    if (group === 'all') {
        return true; // Show all templates if 'all' is selected
    }
    const templateGroups = template['groups'] ? template['groups'].split(',') : [];
    return templateGroups.includes(group);
}

function updateHumanizedTimes() {
    document.querySelectorAll('.humanized-time').forEach(element => {
        const timestamp = element.getAttribute('data-time');
        if (timestamp) {
            element.textContent = timeAgo(timestamp);
        }
    });
}

// Add this function to check if an element is in the viewport
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
    if (attribute === 'data-*') {
        xpath += `[starts-with(@data-,'${value}')]`;
    } else {
        xpath += `[contains(@${attribute},'${value}')]`;
    }

    document.getElementById(inputId).value = xpath;
    document.getElementById(inputId).style.display = 'block';
    document.querySelector(`#${inputId} + .structured-xpath-input`).remove();
}

function loadGroups() {
    fetch('/groups')
        .then(response => response.json())
        .then(groups => {
            const groupDropdown = document.getElementById('group-dropdown');
            groupDropdown.innerHTML = '<option value="all">All Groups</option>';
            groups.forEach(group => {
                const option = document.createElement('option');
                option.value = group;
                option.textContent = group;
                groupDropdown.appendChild(option);
            });
        })
        .catch(error => console.error('Error loading groups:', error));
}

function setupSearch() {
    const searchInput = document.getElementById('search-input');
    const groupDropdown = document.getElementById('group-dropdown');
    const cameraRows = document.querySelectorAll('.camera-row');

    function filterCameras() {
        const searchTerm = searchInput.value.toLowerCase();
        const selectedGroup = groupDropdown.value;

        cameraRows.forEach(row => {
            const name = row.querySelector('td:first-child').textContent.toLowerCase();
            const groups = row.dataset.groups.split(',');
            const matchesSearch = name.includes(searchTerm);
            const matchesGroup = selectedGroup === 'all' || groups.includes(selectedGroup);

            row.style.display = matchesSearch && matchesGroup ? '' : 'none';
        });
    }

    searchInput.addEventListener('input', filterCameras);
    groupDropdown.addEventListener('change', filterCameras);
}

if (groupDropdown) {
function loadTemplates() {
    const selectedGroup = document.getElementById('group-dropdown').value || 'all';
    const searchQuery = document.getElementById('search-input').value.toLowerCase();
    const url = `/templates?group=${selectedGroup}&search=${searchQuery}&t=${new Date().getTime()}`;

    updateGridLayout();

    const templateList = document.getElementById('template-list');
    const captionsTable = document.querySelector('details table');
    const templateContainer = document.querySelector('.template-container');

    // Determine which page we're on
    const isIndexPage = !!templateList;
    const isCaptionsPage = !!captionsTable && !!templateContainer;

    // Show loading indicator
    if (isIndexPage) {
        templateList.innerHTML = '<div class="loading">Loading templates...</div>';
    } else if (isCaptionsPage) {
        templateContainer.innerHTML = '<div class="loading">Loading templates...</div>';
    }

    fetch(url)
        .then(response => response.json())
        .then(templates => {
            // Clear loading indicator
            if (isIndexPage) {
                templateList.innerHTML = '';
            } else if (isCaptionsPage) {
                templateContainer.innerHTML = '';
            }

            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (isMobile() && entry.isIntersecting) {
                        const video = entry.target;
                        video.play();
                    } else {
                        entry.target.pause();
                    }
                });
            }, {
                threshold: 0.5 // Trigger when at least 50% of the video is visible
            });

            Object.entries(templates).forEach(([name, template], index) => {
                if (templateBelongsToGroup(template, selectedGroup) && templateMatchesSearch(template, searchQuery)) {
                    const lastScreenshotTime = template['last_screenshot_time'];
                    const humanizedTimestamp = timeAgo(lastScreenshotTime);
                    const nextCaptureTime = timeAgo(template['next_screenshot_time']);

                    // Check if the last screenshot is less than 1 minute ago
                    const lastScreenshotTime2 = new Date(template['last_screenshot_time']);
                    const oneMinuteAgo = new Date(Date.now() - 60000);
                    const isRecent = lastScreenshotTime2 > oneMinuteAgo;
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
                                    <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" style='width:100%' muted title='${template["last_caption"]} (${humanizedTimestamp})' preload="none">
                                        <source src="/last_video/${name}" type='video/mp4'>
                                        Your browser does not support the video tag.
                                    </video>
                                    <div class="timestamp" title="${formatExactTime(lastScreenshotTime)}">${humanizedTimestamp}</div>
                                    <div class="play-icon">&#9658;</div>
                                </div>
                            </a>
                        `;
                        templateList.appendChild(templateDiv);

                        // Trigger reflow to enable transition
                        void templateDiv.offsetWidth;

                        // Add fade-in effect with delay based on index
                        setTimeout(() => {
                            templateDiv.style.opacity = '1';
                            templateDiv.style.transform = 'translateY(0)';
                        }, index * 100);

                        // Add event listeners for hover
                        const video = templateDiv.querySelector('video');
                        observer.observe(video);

                        // Add mouseenter and mouseleave event listeners for fast playback
                        video.addEventListener('mouseenter', () => {
                            video.playbackRate = 2.0; // Play at 2x speed on hover
                            video.play();
                        });

                        video.addEventListener('mouseleave', () => {
                            video.playbackRate = 1.0; // Reset to normal speed
                            video.pause();
                        });

                        // ... (rest of the video event listeners)
                    } else if (isCaptionsPage) {
                        const templateDiv = document.createElement('div');
                        templateDiv.classList.add("templateDiv");
                        templateDiv.innerHTML = `
                            <img src="/last_screenshot/${name}" alt="${name}" style='width:100%'>
                            <div class="camera-name">${name}</div>
                            <div class="timestamp" title="${formatExactTime(lastScreenshotTime)}">Last: ${humanizedTimestamp}</div>
                            <div class="next-capture">Next: ${nextCaptureTime}</div>
                            <textarea class="notes-textarea" id="notes-${name}" name="notes">${template['notes']}</textarea>
                            <button class="update-button" type="button" onclick="updateTemplate('${name}')">Update</button>
                        `;
                        templateContainer.appendChild(templateDiv);
                    }
                }
            });

            if (isIndexPage) {
                window.addEventListener('resize', updateGridLayout);
            }

            // Update humanized times for captions page
            if (isCaptionsPage) {
                updateHumanizedTimes();
            }
        })
        .catch(error => {
            console.error('Error loading templates:', error);
            if (isIndexPage) {
                templateList.innerHTML = '<div class="error">Error loading templates. Please try again.</div>';
            } else if (isCaptionsPage) {
                templateContainer.innerHTML = '<div class="error">Error loading templates. Please try again.</div>';
            }
        });
}

function templateMatchesSearch(template, searchQuery) {
    if (!searchQuery) return true;
    const name = template.name.toLowerCase();
    const groups = template.groups ? template.groups.toLowerCase() : '';
    return name.includes(searchQuery) || groups.includes(searchQuery);
}

// Initial load of templates
loadTemplates();

const groupDropdown = document.getElementById('group-dropdown');

const searchInput = document.getElementById('search-input');

if (groupDropdown) {
    groupDropdown.addEventListener('change', loadTemplates);
}

if (searchInput) {
    searchInput.addEventListener('input', loadTemplates);
}
}

// Set an interval to update video sources every 30 minutes
setInterval(updateVideoSources, 60000*30); // 60000 milliseconds = 1 minute

    // Scheduler toggle functionality
    const toggleSchedulerButton = document.getElementById('toggle-scheduler');
    const schedulerStatus = document.getElementById('scheduler-status');

    if (toggleSchedulerButton) {
        toggleSchedulerButton.addEventListener('click', function() {

            fetch('/toggle_scheduler', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    schedulerStatus.textContent = data.status;
                    toggleSchedulerButton.textContent = data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
                })
                .catch(error => {
                    console.error('Error:', error);
                    schedulerStatus.textContent = 'Error occurred';
                });
        });

        // Initial scheduler status check
        fetch('/scheduler_status')
            .then(response => response.json())
            .then(data => {
                schedulerStatus.textContent = data.status;
                toggleSchedulerButton.textContent = data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
            })
            .catch(error => {
                console.error('Error:', error);
                schedulerStatus.textContent = 'Error occurred';
            });
    }

    // Play All / Stop All functionality
    const toggleAllVideosButton = document.getElementById('toggle-all-videos');
    let isPlaying = false;

    if (toggleAllVideosButton) {
        toggleAllVideosButton.addEventListener('click', function() {
            const videos = document.querySelectorAll('.templateDiv video');
            if (isPlaying) {
                videos.forEach(video => video.pause());
                toggleAllVideosButton.textContent = 'Play All';
            } else {
                videos.forEach(video => video.play());
                toggleAllVideosButton.textContent = 'Stop All';
            }
            isPlaying = !isPlaying;
        });
    }

    // Initialize Cast API
    function initializeCastApi() {
        cast.framework.CastContext.getInstance().setOptions({
            receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
            autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
        });
    }

    // Initialize Google Cast API
    window['__onGCastApiAvailable'] = function(isAvailable) {
        if (isAvailable) {
            initializeCastApi();
        }
    };

    // Start casting
    function startCasting() {
        const castSession = cast.framework.CastContext.getInstance().getCurrentSession();
        if (castSession) {
            const mediaInfo = new chrome.cast.media.MediaInfo(document.getElementById('live-video').src, 'video/mp4');
            const request = new chrome.cast.media.LoadRequest(mediaInfo);
            castSession.loadMedia(request).then(
                function() { console.log('Cast started'); },
                function(errorCode) { console.error('Error code: ' + errorCode); }
            );
        } else {
            console.log('No active cast session');
        }
    }

    // Add event listener for cast button
    const castButton = document.getElementById('cast-button');
    if (castButton) {
        castButton.addEventListener('click', startCasting);
    }
});
