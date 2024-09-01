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
    } else {
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

if (groupDropdown) { 
function loadTemplates() {
    const selectedGroup = document.getElementById('group-dropdown').value || 'all';
    const searchQuery = document.getElementById('search-input').value.toLowerCase();
    const url = `/templates?group=${selectedGroup}&search=${searchQuery}&t=${new Date().getTime()}`;

    updateGridLayout();

    const templateList = document.getElementById('template-list');
    // Show loading indicator
    templateList.innerHTML = '<div class="loading">Loading templates...</div>';

    fetch(url)
        .then(response => response.json())
        .then(templates => {
            // Clear loading indicator
            templateList.innerHTML = '';

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

                    // Check if the last screenshot is less than 1 minute ago
                    const lastScreenshotTime2 = new Date(template['last_screenshot_time']);
                    const oneMinuteAgo = new Date(Date.now() - 60000);
                    const isRecent = lastScreenshotTime2 > oneMinuteAgo;
                    const videoContainerClass = isRecent ? "video-container recent-screenshot" : "video-container";

                    const templateDiv = document.createElement('div');
                    templateDiv.classList.add("templateDiv"); // Add class to div
                    templateDiv.style.opacity = '0';
                    templateDiv.style.transform = 'translateY(20px)';
                    templateDiv.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                    templateDiv.innerHTML = `
                        <a href='/templates/${name}'>
                            <div class="${videoContainerClass}">
                                <div class="camera-name">${name}</div> <!-- Camera name -->
                                <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" style='width:100%' muted title='${template["last_caption"]} (${humanizedTimestamp})' preload="none">
                                    <source src="/last_video/${name}" type='video/mp4'>
                                    Your browser does not support the video tag.
                                </video>
                                <div class="timestamp" title="${formatExactTime(lastScreenshotTime)}">${humanizedTimestamp}</div> <!-- Humanized timestamp in the bottom right corner with tooltip -->
                                <div class="play-icon">&#9658;</div> <!-- Unicode play icon -->
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

                    video.addEventListener('loadedmetadata', () => {
                        // Set playback speed based on video duration
                        if (video.duration < 1) {
                            video.playbackRate = 0.0625;
                        } else if (video.duration < 3) {
                            video.playbackRate = 0.0625*2;
                        } else if (video.duration < 7) {
                            video.playbackRate = 0.0625*4;
                        } else if (video.duration < 15) {
                            video.playbackRate = 0.0625*8;
                        } else if (video.duration < 30) {
                            video.playbackRate = 0.0625*16;
                        } else if (video.duration < 60) {
                            video.playbackRate = 0.0625*32;
                        } else if (video.duration > 120) {
                            video.playbackRate = 0.0625*64;
                        } else {
                            video.playbackRate = 0.0625*128;
                        }

                        // Start the video at t minus 10 seconds if possible
                        video.currentTime = Math.max(0, video.duration - 10);
                    });

                    if (isMobile()) {
                        video.setAttribute('playsinline', ''); // Prevent fullscreen playback on iOS
                        video.addEventListener('play', () => {
                            video.playbackRate = calculatePlaybackRate(video); // Set appropriate playback rate
                        });
                    } else {
                        video.addEventListener('mouseenter', () => {
                            if (video.playbackRate * 3.0 <= 16) {
                                video.playbackRate *= 3.0; // Set playback speed
                            } else {
                                video.playbackRate = 16; // Set playback rate to max value of 16
                            }
                            video.play();
                        });

                        video.addEventListener('mouseleave', () => {
                            video.pause();
                            video.load(); // Reset the video to show the poster again
                        });
                    }

                    video.addEventListener('ended', () => {
                        setTimeout(() => {
                            video.load(); // Reset the video to show the poster
                            video.play(); // Resume autoplay after 1 second
                        }, 2000); // Pause for 1 second
                    });
                }
            });

            const playAllButton = document.getElementById('play-all');
            const stopAllButton = document.getElementById('stop-all');

            // Play all media elements
            playAllButton.addEventListener('click', function () {
                const mediaElements = templateList.querySelectorAll('video, audio');
                mediaElements.forEach(element => {
                    element.play();
                });
            });

            // Stop all media elements
            stopAllButton.addEventListener('click', function () {
                const mediaElements = templateList.querySelectorAll('video, audio');
                mediaElements.forEach(element => {
                    element.pause();
                    element.currentTime = 0; // Reset to start
                });
            });

            window.addEventListener('resize', updateGridLayout);
        })
        .catch(error => {
            console.error('Error loading templates:', error);
            templateList.innerHTML = '<div class="error">Error loading templates. Please try again.</div>';
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
loadGroups();

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

});
