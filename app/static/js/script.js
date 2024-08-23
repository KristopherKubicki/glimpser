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
            // Clear existing options
            groupDropdown.innerHTML = '';
            // Create and append the "All Groups" option
            const allOption = document.createElement('option');
            allOption.value = 'all';
            allOption.textContent = 'All Groups';
            groupDropdown.appendChild(allOption);
            // Create and append options for each group
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
            // Clear existing templates
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

            Object.entries(templates).forEach(([name, template]) => {
	      if (templateBelongsToGroup(template, selectedGroup)) {

	        const lastScreenshotTime = template['last_screenshot_time'];
                const humanizedTimestamp = timeAgo(lastScreenshotTime);


                // Check if the last screenshot is less than 1 minute ago
                const lastScreenshotTime2 = new Date(template['last_screenshot_time']);
                const oneMinuteAgo = new Date(Date.now() - 60000);
                const isRecent = lastScreenshotTime2 > oneMinuteAgo;
                const videoContainerClass = isRecent ? "video-container recent-screenshot" : "video-container";

                const templateDiv = document.createElement('div');
                templateDiv.classList.add("templateDiv"); // Add class to div
                
                const link = document.createElement('a');
                link.href = `/templates/${name}`;
                
                const videoContainer = document.createElement('div');
                videoContainer.className = videoContainerClass;
                
                const cameraName = document.createElement('div');
                cameraName.className = 'camera-name';
                cameraName.textContent = name;
                videoContainer.appendChild(cameraName);
                
                const video = document.createElement('video');
                video.setAttribute('data-name', name);
                video.setAttribute('poster', `/last_screenshot/${name}`);
                video.setAttribute('alt', name);
                video.style.width = '100%';
                video.muted = true;
                video.title = template["last_caption"];
                video.setAttribute('preload', 'none');
                
                const source = document.createElement('source');
                source.src = `/last_video/${name}`;
                source.type = 'video/mp4';
                video.appendChild(source);
                
                const fallbackText = document.createTextNode('Your browser does not support the video tag.');
                video.appendChild(fallbackText);
                
                videoContainer.appendChild(video);
                
                const timestamp = document.createElement('div');
                timestamp.className = 'timestamp';
                timestamp.textContent = humanizedTimestamp;
                videoContainer.appendChild(timestamp);
                
                const playIcon = document.createElement('div');
                playIcon.className = 'play-icon';
                playIcon.textContent = '▶';
                videoContainer.appendChild(playIcon);
                
                link.appendChild(videoContainer);
                templateDiv.appendChild(link);
                templateList.appendChild(templateDiv);

                // Add event listeners for hover
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
            ///video.setAttribute('autoplay', ''); // Enable autoplay on mobile
            video.setAttribute('playsinline', ''); // Prevent fullscreen playback on iOS
            video.addEventListener('play', () => {
                video.playbackRate = calculatePlaybackRate(video); // Set appropriate playback rate
            });
        } else {
            // Your existing mouseenter and mouseleave event listeners...
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

    // Add event listeners for each video
    const videos = document.querySelectorAll('.templateDiv video');
    videos.forEach(video => {
        // Play video on hover
        video.addEventListener('mouseenter', () => {
            video.play();
        });
        // Pause video on mouse leave
        video.addEventListener('mouseleave', () => {
            video.pause();
        });
        // Use the observer to play/pause based on visibility
        observer.observe(video);
    });

        }

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

video.addEventListener('ended', () => {
    setTimeout(() => {
        video.load(); // Reset the video to show the poster
        video.play(); // Resume autoplay after 1 second
    }, 2000); // Pause for 1 second
});

}
            });

        })
        .catch(error => console.error('Error loading templates:', error));
}

// Initial load of templates
loadTemplates();
loadGroups();

groupDropdown.addEventListener('change', loadTemplates);

// Set an interval to update video sources every 30 minutes
setInterval(updateVideoSources, 60000*30); // 60000 milliseconds = 1 minute

});
