// Adaptive Bitrate Streaming

const qualityLevels = ['low', 'medium', 'high'];

function getOptimalQuality(networkSpeed) {
    if (networkSpeed < 1) {
        return 'low';
    } else if (networkSpeed < 5) {
        return 'medium';
    } else {
        return 'high';
    }
}

function updateVideoSource(video, quality) {
    const name = video.getAttribute('data-name');
    const newSource = `/video/${name}/${quality}?t=${new Date().getTime()}`;
    video.src = newSource;
}

function setupAdaptiveStreaming(video, networkSpeed) {
    const quality = getOptimalQuality(networkSpeed);
    updateVideoSource(video, quality);
}

export { setupAdaptiveStreaming };