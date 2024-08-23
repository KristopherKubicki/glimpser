// app/static/js/script.js

// Function definitions
function updateGridLayout() {
    const templateList = document.getElementById('template-list');
    if (isMobile()) {
        templateList.style.gridTemplateColumns = '1fr'; // Set to single column layout
    } else {
        templateList.style.gridTemplateColumns = 'repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))'; // Set to dynamic column layout
    }
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

function isMobile() {
    return window.matchMedia("(hover: none)").matches;
}

function updateVideoSources() {
    const videos = document.querySelectorAll('.templateDiv video');
    videos.forEach(video => {
        const name = video.getAttribute('data-name');
        const newSource = `/last_video/${name}?t=${new Date().getTime()}`;
        const newPoster = `/last_screenshot/${name}?t=${new Date().getTime()}`;
        const source = video.querySelector('source');
        source.src = newSource;
        video.poster = newPoster;
    });
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
                    if (isMobile() && entry.isIntersecting) {
                        entry.target.play();
                    } else {
                        entry.target.pause();
                    }
                });
            }, { threshold: 0.5 });

            Object.entries(templates).forEach(([name, template]) => {
                if (templateBelongsToGroup(template, selectedGroup)) {
                    const templateDiv = createTemplateDiv(name, template);
                    templateList.appendChild(templateDiv);

                    const video = templateDiv.querySelector('video');
                    setupVideoEventListeners(video, observer);
                }
            });
        })
        .catch(error => console.error('Error loading templates:', error));
}

function createTemplateDiv(name, template) {
    const lastScreenshotTime = new Date(template['last_screenshot_time']);
    const humanizedTimestamp = timeAgo(lastScreenshotTime);
    const isRecent = lastScreenshotTime > new Date(Date.now() - 60000);
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
    return templateDiv;
}

function setupVideoEventListeners(video, observer) {
    observer.observe(video);

    video.addEventListener('loadedmetadata', () => {
        setPlaybackRate(video);
        video.currentTime = Math.max(0, video.duration - 10);
    });

    if (isMobile()) {
        video.setAttribute('playsinline', '');
        video.addEventListener('play', () => setPlaybackRate(video));
    } else {
        video.addEventListener('mouseenter', () => {
            setPlaybackRate(video);
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
}

function setPlaybackRate(video) {
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
}

document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('#template-form form');
    const groupDropdown = document.getElementById('group-dropdown');
    const slider = document.getElementById('grid-width-slider');
    const templateList = document.getElementById('template-list');

    groupDropdown.addEventListener('change', () => {
        console.log('Group changed to:', groupDropdown.value);
        loadTemplates();
    });

    slider.addEventListener('input', function () {
        const value = Math.max(100, parseInt(slider.value));
        const pxValue = value + 'px';
        templateList.style.setProperty('--grid-item-width', pxValue);
        updateGridLayout();
        const fontSizeBase = Math.max(8, Math.min(14, value / 25));
        document.documentElement.style.setProperty('--font-size-base', `${fontSizeBase}px`);
    });

    window.addEventListener('resize', updateGridLayout);

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
            loadTemplates();
            form.reset();
        })
        .catch((error) => {
            console.error('Error:', error);
        });
    });

    updateGridLayout();
    loadTemplates();
    loadGroups();
});

// Set an interval to update video sources every 30 minutes
setInterval(updateVideoSources, 60000*30);
