// Network Speed Detection

let currentNetworkSpeed = 0;

function measureNetworkSpeed(callback) {
    const imageAddr = "https://example.com/test-image.jpg" + "?n=" + Math.random();
    const downloadSize = 5245329; // bytes

    let startTime, endTime;
    const download = new Image();
    download.onload = function () {
        endTime = (new Date()).getTime();
        const duration = (endTime - startTime) / 1000;
        const bitsLoaded = downloadSize * 8;
        const speedBps = (bitsLoaded / duration).toFixed(2);
        const speedKbps = (speedBps / 1024).toFixed(2);
        const speedMbps = (speedKbps / 1024).toFixed(2);
        callback(speedMbps);
    }

    startTime = (new Date()).getTime();
    download.src = imageAddr;
}

function updateNetworkSpeed() {
    measureNetworkSpeed((speed) => {
        currentNetworkSpeed = parseFloat(speed);
        console.log(`Current network speed: ${currentNetworkSpeed} Mbps`);
    });
}

// Update network speed every 5 minutes
setInterval(updateNetworkSpeed, 5 * 60 * 1000);

// Initial network speed measurement
updateNetworkSpeed();

export { currentNetworkSpeed };