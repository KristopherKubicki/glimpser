// app/static/js/script.js

document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('#template-form form');

    const groupDropdown = document.getElementById('group-dropdown');
    groupDropdown.addEventListener('change', () => {
	     console.log('Group changed to:', groupDropdown.value);
        loadTemplates(); // Reload templates based on the selected group
    });

    const slider = document.getElementById('grid-width-slider');
    const templateList = document.getElementById('template-list');

    slider.addEventListener('input', function () {
        const value = slider.value + 'px';
        templateList.style.setProperty('--grid-item-width', value);
    });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

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
        })
        .catch((error) => {
            console.error('Error:', error);
        });
    });

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


function timeAgo(dateString) {
    const now = new Date();
    const date = new Date(dateString);
    const seconds = Math.floor((now - date) / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(days / 365);

    if (seconds < 60) {
        return `${seconds} seconds ago`;
    } else if (minutes < 60) {
        return `${minutes} minutes ago`;
    } else if (hours < 24) {
        return `${hours} hours ago`;
    } else if (days < 30) {
        return `${days} days ago`;
    } else if (months < 12) {
        return `${months} months ago`;
    } else {
        return `${years} years ago`;
    }
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


function loadTemplates() {
    const selectedGroup = document.getElementById('group-dropdown').value || 'all';
    const url = selectedGroup === 'all' ? '/templates' : `/templates?group=${selectedGroup}&t=${new Date().getTime()}`;

    updateGridLayout();

    fetch('/templates')
        .then(response => response.json())
        .then(templates => {
            const templateList = document.getElementById('template-list');
            templateList.innerHTML = '';

            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    const video = entry.target;
                    if (entry.isIntersecting) {
                        if (isMobile()) {
                            video.play().catch(e => console.log("Autoplay prevented:", e));
                        }
                    } else {
                        video.pause();
                    }
                });
            }, {
                threshold: 0.5
            });

            Object.entries(templates).forEach(([name, template]) => {
                if (templateBelongsToGroup(template, selectedGroup)) {
                    const lastScreenshotTime = template['last_screenshot_time'];
                    const humanizedTimestamp = timeAgo(lastScreenshotTime);

                    const lastScreenshotTime2 = new Date(template['last_screenshot_time']);
                    const oneMinuteAgo = new Date(Date.now() - 60000);
                    const isRecent = lastScreenshotTime2 > oneMinuteAgo;
                    const videoContainerClass = isRecent ? "video-container recent-screenshot" : "video-container";

                    const templateDiv = document.createElement('div');
                    templateDiv.classList.add("templateDiv");
                    templateDiv.innerHTML = `
                        <a href='/templates/${name}'>
                            <div class="${videoContainerClass}">
                                <div class="camera-name">${name}</div>
                                <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" muted playsinline preload="none">
                                    <source src="/last_video/${name}" type='video/mp4'>
                                    Your browser does not support the video tag.
                                </video>
                                <div class="timestamp">${humanizedTimestamp}</div>
                                <div class="play-icon">&#9658;</div>
                            </div>
                        </a>
                    `;
                    templateList.appendChild(templateDiv);

                    const video = templateDiv.querySelector('video');
                    observer.observe(video);

                    video.addEventListener('loadedmetadata', () => {
                        setPlaybackRate(video);
                        video.currentTime = Math.max(0, video.duration - 10);
                    });

                    if (!isMobile()) {
                        video.addEventListener('mouseenter', () => {
                            setPlaybackRate(video);
                            video.play().catch(e => console.log("Playback prevented:", e));
                        });

                        video.addEventListener('mouseleave', () => {
                            video.pause();
                            video.currentTime = 0;
                        });
                    }

                    video.addEventListener('ended', () => {
                        setTimeout(() => {
                            video.currentTime = 0;
                            video.play().catch(e => console.log("Replay prevented:", e));
                        }, 2000);
                    });
                }
            });

            setupPlaybackControls(templateList);
        })
        .catch(error => console.error('Error loading templates:', error));
}

function setPlaybackRate(video) {
    if (video.duration < 1) {
        video.playbackRate = 0.0625;
    } else if (video.duration < 3) {
        video.playbackRate = 0.125;
    } else if (video.duration < 7) {
        video.playbackRate = 0.25;
    } else if (video.duration < 15) {
        video.playbackRate = 0.5;
    } else if (video.duration < 30) {
        video.playbackRate = 1;
    } else if (video.duration < 60) {
        video.playbackRate = 2;
    } else if (video.duration > 120) {
        video.playbackRate = 4;
    } else {
        video.playbackRate = 8;
    }
}

function setupPlaybackControls(templateList) {
    const playAllButton = document.getElementById('play-all');
    const stopAllButton = document.getElementById('stop-all');

    playAllButton.addEventListener('click', () => {
        templateList.querySelectorAll('video').forEach(video => {
            video.play().catch(e => console.log("Playback prevented:", e));
        });
    });

    stopAllButton.addEventListener('click', () => {
        templateList.querySelectorAll('video').forEach(video => {
            video.pause();
            video.currentTime = 0;
        });
    });
}

// Initial load of templates
loadTemplates();
loadGroups();

const groupDropdown = document.getElementById('group-dropdown');
groupDropdown.addEventListener('change', loadTemplates);

window.addEventListener('resize', updateGridLayout);

// Set an interval to update video sources every 30 minutes
setInterval(updateVideoSources, 60000 * 30);

});
