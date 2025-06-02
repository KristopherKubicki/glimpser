// tests/js/live_error.test.js

document.body.innerHTML = `
  <div id="video-overlay" style="display:none;">
    <div id="loading-indicator" style="display:none;"></div>
    <div id="play-pause-indicator" style="display:none;"></div>
    <div id="offline-indicator" style="display:none;"></div>
    <div id="capture-error-indicator" style="display:none;"></div>
    <div id="stream-error-indicator" class="error-indicator hidden" style="display:none;">
      <p id="stream-error-message"></p>
    </div>
  </div>
`;

const videoOverlay = document.getElementById('video-overlay');
const loadingIndicator = document.getElementById('loading-indicator');
const playPauseIndicator = document.getElementById('play-pause-indicator');
const offlineIndicator = document.getElementById('offline-indicator');
const errorIndicator = document.getElementById('capture-error-indicator');
const streamErrorIndicator = document.getElementById('stream-error-indicator');
const streamErrorMessage = document.getElementById('stream-error-message');

function showStreamErrorIndicator(message) {
  videoOverlay.style.display = 'block';
  streamErrorIndicator.style.display = 'block';
  streamErrorMessage.textContent = message;
  loadingIndicator.style.display = 'none';
  playPauseIndicator.style.display = 'none';
}

function hideStreamErrorIndicator() {
  streamErrorIndicator.style.display = 'none';
  streamErrorMessage.textContent = '';
  if (
    loadingIndicator.style.display === 'none' &&
    playPauseIndicator.style.display === 'none' &&
    offlineIndicator.style.display === 'none' &&
    errorIndicator.style.display === 'none'
  ) {
    videoOverlay.style.display = 'none';
  }
}

function showError(e) {
  let message = 'Error loading stream';
  if (e && e.target && e.target.error) {
    switch (e.target.error.code) {
      case 2:
        message = 'Network error while loading stream';
        break;
      case 4:
        message = 'Video format not supported';
        break;
      default:
        message = 'Error loading stream';
    }
  } else if (typeof e === 'string') {
    message = e;
  }
  showStreamErrorIndicator(message);
}

describe('showError overlay', () => {
  beforeEach(() => {
    hideStreamErrorIndicator();
  });

  test('displays network error message', () => {
    const event = { target: { error: { code: 2 } } };
    showError(event);
    expect(streamErrorIndicator.style.display).toBe('block');
    expect(streamErrorMessage.textContent).toBe('Network error while loading stream');
  });

  test('displays unsupported format message', () => {
    const event = { target: { error: { code: 4 } } };
    showError(event);
    expect(streamErrorIndicator.style.display).toBe('block');
    expect(streamErrorMessage.textContent).toBe('Video format not supported');
  });
});
