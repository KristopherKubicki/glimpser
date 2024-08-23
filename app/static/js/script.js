// app/static/js/script.js

document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('#template-form form');

    const groupDropdown = document.getElementById('group-dropdown');
    groupDropdown.addEventListener('change', () => {
	     console.log('Group changed to:', groupDropdown.value);
        allTemplatesLoaded = false;
        page = 1;
        loadTemplates(); // Reload templates based on the selected group
    });

    // Infinite scroll
    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
            loadTemplates(true);
        }
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

    // Dark mode toggle functionality
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const body = document.body;

    darkModeToggle.addEventListener('click', () => {
        body.classList.toggle('dark-mode');
        localStorage.setItem('dark-mode', body.classList.contains('dark-mode'));
    });

    // Check for saved dark mode preference
    if (localStorage.getItem('dark-mode') === 'true') {
        body.classList.add('dark-mode');
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


function timeAgo(date) {
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);

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


let page = 1;
const templatesPerPage = 20;
let loading = false;
let allTemplatesLoaded = false;

function showLoadingIndicator() {
    document.getElementById('loading-indicator').style.display = 'block';
}

function hideLoadingIndicator() {
    document.getElementById('loading-indicator').style.display = 'none';
}

let allTemplates = {};

function loadTemplates(append = false) {
    if (loading || allTemplatesLoaded) return;

    loading = true;
    showLoadingIndicator();
    const selectedGroup = document.getElementById('group-dropdown').value || 'all';
    const url = selectedGroup === 'all' ? `/templates?page=${page}&per_page=${templatesPerPage}` : `/templates?group=${selectedGroup}&page=${page}&per_page=${templatesPerPage}&t=${new Date().getTime()}`;

    updateGridLayout();

    fetch(url)
        .then(response => response.json())
        .then(templates => {
            allTemplates = { ...allTemplates, ...templates };
            renderTemplates(templates, append);

            if (Object.keys(templates).length < templatesPerPage) {
                allTemplatesLoaded = true;
            }

            page++;
            loading = false;
            hideLoadingIndicator();
        })
        .catch(error => {
            console.error('Error loading templates:', error);
            loading = false;
            hideLoadingIndicator();
        });
}

function renderTemplates(templates, append = false) {
    const templateList = document.getElementById('template-list');
    if (!append) {
        templateList.innerHTML = '';
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
        threshold: 0.5
    });

    Object.entries(templates).forEach(([name, template]) => {
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
                    <video data-name="${name}" poster="/last_screenshot/${name}" alt="${name}" style='width:100%' muted title='${template["last_caption"]}' preload="none">
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

            video.currentTime = Math.max(0, video.duration - 10);
        });

        if (isMobile()) {
            video.setAttribute('playsinline', '');
            video.addEventListener('play', () => {
                video.playbackRate = calculatePlaybackRate(video);
            });
        } else {
            video.addEventListener('mouseenter', () => {
                if (video.playbackRate * 3.0 <= 16) {
                    video.playbackRate *= 3.0;
                } else {
                    video.playbackRate = 16;
                }
                video.play();
            });

            video.addEventListener('mouseleave', () => {
                video.pause();
                video.load();
            });
        }

        video.addEventListener('ended', () => {
            setTimeout(() => {
                video.load();
                video.play();
            }, 2000);
        });
    });
}

function searchTemplates() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const filteredTemplates = Object.entries(allTemplates).reduce((acc, [name, template]) => {
        if (name.toLowerCase().includes(searchTerm) || template.last_caption.toLowerCase().includes(searchTerm)) {
            acc[name] = template;
        }
        return acc;
    }, {});
    renderTemplates(filteredTemplates);
}

document.getElementById('search-input').addEventListener('input', searchTemplates);

// Infinite scroll
window.addEventListener('scroll', () => {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
        loadTemplates(true);
    }
});

// Initial load of templates
loadTemplates();
loadGroups();

groupDropdown.addEventListener('change', () => {
    allTemplatesLoaded = false;
    loadTemplates();
});

// Set an interval to update video sources every 30 minutes
setInterval(updateVideoSources, 60000*30);

// Define playAllVideos and stopAllVideos functions
function playAllVideos() {
    const mediaElements = document.querySelectorAll('video, audio');
    mediaElements.forEach(element => {
        element.play();
    });
}

function stopAllVideos() {
    const mediaElements = document.querySelectorAll('video, audio');
    mediaElements.forEach(element => {
        element.pause();
        element.currentTime = 0;
    });
}

// Add event listeners for play-all and stop-all buttons
playAllButton.addEventListener('click', playAllVideos);
stopAllButton.addEventListener('click', stopAllVideos);

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return; // Don't trigger shortcuts when typing in input fields
    }

    switch (e.key) {
        case 'p':
            playAllVideos();
            break;
        case 's':
            stopAllVideos();
            break;
        case 'd':
            document.getElementById('dark-mode-toggle').click();
            break;
        case '/':
            e.preventDefault();
            document.getElementById('search-input').focus();
            break;
        case 'Escape':
            document.getElementById('search-input').value = '';
            searchTemplates();
            break;
        case '?':
            e.preventDefault();
            toggleShortcutTooltip();
            break;
    }
});

// Add tooltip to show keyboard shortcuts
const shortcutTooltip = document.createElement('div');
shortcutTooltip.id = 'shortcut-tooltip';
shortcutTooltip.style.display = 'none';
shortcutTooltip.innerHTML = `
    <h3>Keyboard Shortcuts</h3>
    <ul>
        <li><strong>P</strong>: Play all videos</li>
        <li><strong>S</strong>: Stop all videos</li>
        <li><strong>D</strong>: Toggle dark mode</li>
        <li><strong>/</strong>: Focus search input</li>
        <li><strong>Esc</strong>: Clear search</li>
        <li><strong>?</strong>: Toggle this tooltip</li>
    </ul>
`;
document.body.appendChild(shortcutTooltip);

function toggleShortcutTooltip() {
    shortcutTooltip.style.display = shortcutTooltip.style.display === 'none' ? 'block' : 'none';
}

// Add click event listener to the "Show Keyboard Shortcuts" button
document.getElementById('show-shortcuts').addEventListener('click', toggleShortcutTooltip);

const playAllButton = document.getElementById('play-all');
const stopAllButton = document.getElementById('stop-all');

playAllButton.addEventListener('click', playAllVideos);
stopAllButton.addEventListener('click', stopAllVideos);

window.addEventListener('resize', updateGridLayout);

});
