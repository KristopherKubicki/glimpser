export function initVideoControls() {
  document.addEventListener('DOMContentLoaded', () => {
    setupStatusPageVideoHover();
    setupVideoControls();

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

    setInterval(updateVideoSources, 60000 * 30);
  });

  window.__onGCastApiAvailable = function(isAvailable) {
    if (isAvailable) initializeCastApi();
  };
}

export function updateVideoSources() {
  const videos = document.querySelectorAll('.templateDiv video');
  videos.forEach((video) => {
    const name = video.getAttribute('data-name');
    const timestamp = new Date().getTime();
    video.querySelector('source').src = `/last_video/${name}?t=${timestamp}`;
    video.poster = `/last_screenshot/${name}?t=${timestamp}`;
  });
}

export function setupVideoControls() {
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

  document.addEventListener('keydown', (e) => {
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    switch (e.key) {
      case ' ': // Spacebar
      case 'k':
        e.preventDefault();
        video.paused ? video.play() : video.pause();
        break;
      case 'm':
        video.muted = !video.muted;
        break;
      case 'f':
        if (video.requestFullscreen) video.requestFullscreen();
        else if (video.mozRequestFullScreen) video.mozRequestFullScreen();
        else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
        else if (video.msRequestFullscreen) video.msRequestFullscreen();
        break;
      default:
        break;
    }
  });
}

export function setupStatusPageVideoHover() {
  const thumbnailVideoCells = document.querySelectorAll('.thumbnail-video');
  thumbnailVideoCells.forEach((cell) => {
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

export function initializeCastApi() {
  cast.framework.CastContext.getInstance().setOptions({
    receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
    autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
  });
}

export function startCasting() {
  const castSession = cast.framework.CastContext.getInstance().getCurrentSession();
  if (castSession) {
    const mediaInfo = new chrome.cast.media.MediaInfo(
      document.getElementById('live-video').src,
      'video/mp4'
    );
    const request = new chrome.cast.media.LoadRequest(mediaInfo);
    castSession.loadMedia(request).then(
      () => console.log('Cast started'),
      (errorCode) => console.error('Error code: ' + errorCode)
    );
  } else {
    console.log('No active cast session');
  }
}
