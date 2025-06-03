export function initNav() {
  document.addEventListener('DOMContentLoaded', () => {
    const healthStatus = document.getElementById('health-status');
    const dangerStatus = document.getElementById('danger-status');
    const discoveryStatus = document.getElementById('discover-status');
    const nav = document.querySelector('nav');
    const menuToggle = document.getElementById('menu-toggle');

    if (nav && menuToggle) {
      menuToggle.addEventListener('click', () => {
        nav.classList.toggle('active');
      });
    }

    const checkHealth = async () => {
      if (!healthStatus) return;
      try {
        const res = await fetch('/health');
        const data = await res.json();
        if (data.status === 'healthy') {
          healthStatus.style.color = 'green';
          healthStatus.title = 'System Status: Healthy\n\n';
        } else {
          healthStatus.style.color = 'red';
          healthStatus.title = 'System Status: Degraded\n\n';
        }
        healthStatus.title +=
          `CPU: ${data.metrics.cpu_usage}%\n` +
          `Memory: ${data.metrics.memory_usage}%\n` +
          `Disk: ${data.metrics.disk_usage}%\n` +
          `Open Files: ${data.metrics.open_files}\n` +
          `Threads: ${data.metrics.thread_count}\n` +
          `Uptime: ${data.metrics.uptime}\n`;
        if (data.error_messages?.length) {
          healthStatus.title += `\nErrors:\n${data.error_messages.join('\n')}`;
        }
      } catch (error) {
        console.error('Error fetching health status:', error);
        healthStatus.style.color = 'red';
        healthStatus.title = 'Error: Unable to fetch health status';
      }
    };

    const checkDanger = async () => {
      if (!dangerStatus) return;
      try {
        const res = await fetch('/danger_status');
        const data = await res.json();
        if (data.ready) {
          dangerStatus.style.color = 'orange';
          dangerStatus.title = 'Danger Mode Ready';
        } else {
          dangerStatus.style.color = 'grey';
          const reason = [];
          if (!data.port_open) reason.push('Debug port closed');
          if (!data.idle) reason.push('User active');
          dangerStatus.title = 'Danger Mode Off';
          if (reason.length) dangerStatus.title += `\n${reason.join(', ')}`;
        }
      } catch (error) {
        console.error('Error fetching danger status:', error);
      }
    };


    const captionsIcon = document.getElementById('captions');
    let lastCaptionTime = null;
    const checkCaptions = async () => {
      if (!captionsIcon) return;
      try {
        const res = await fetch('/captions_status');
        const data = await res.json();
        captionsIcon.title = data.caption || '';
        if (data.timestamp) {
          const ts = new Date(data.timestamp.replace(' ', 'T') + 'Z');
          if (!lastCaptionTime || ts > lastCaptionTime) {
            captionsIcon.classList.add('flash-caption');
            setTimeout(() => captionsIcon.classList.remove('flash-caption'), 5000);
            lastCaptionTime = ts;
          }
          const ageSec = (Date.now() - ts.getTime()) / 1000;
          if (ageSec < 60) {
            captionsIcon.style.color = 'green';
          } else if (ageSec < 300) {
            captionsIcon.style.color = 'yellow';
          } else if (ageSec > 1800) {
            captionsIcon.style.color = 'red';
          } else {
            captionsIcon.style.color = '';
          }
        }
      } catch (error) {
        console.error('Error fetching caption status:', error);
      }
    };

    const checkDiscovery = async () => {
      if (!discoveryStatus) return;
      try {
        const res = await fetch('/discovery_status');
        const data = await res.json();
        const fmt = (s) => `${Math.round(s / 60)}m`;
        if (data.status === 'none') {
          discoveryStatus.style.color = 'white';
        } else if (data.status === 'running') {
          discoveryStatus.style.color = 'orange';
        } else if (data.status === 'ready') {
          discoveryStatus.style.color = 'green';
        } else if (data.status === 'error') {
          discoveryStatus.style.color = 'red';
        } else {
          discoveryStatus.style.color = 'grey';
        }
        let title = `Background discovery: ${data.status}`;
        if (data.running_for) {
          title += `\nRunning for ${fmt(data.running_for)}`;
        } else if (Number.isFinite(data.age) && data.status !== 'none') {
          title += `\nLast run ${fmt(data.age)} ago`;
        }
        if (data.next_run_in) {
          title += `\nNext in ${fmt(data.next_run_in)}`;
        }
        discoveryStatus.title = title;
      } catch (error) {
        console.error('Error fetching discovery status:', error);
        discoveryStatus.style.color = 'red';
      }
    };

    const updateCoolClock = () => {
      const now = new Date();
      const secondsDegrees = (now.getSeconds() / 60) * 360;
      const minutesDegrees = (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
      const hoursDegrees = (now.getHours() / 12) * 360 + (now.getMinutes() / 60) * 30;

      document.querySelector('.second-hand').style.transform = `rotate(${secondsDegrees}deg)`;
      document.querySelector('.minute-hand').style.transform = `rotate(${minutesDegrees}deg)`;
      document.querySelector('.hour-hand').style.transform = `rotate(${hoursDegrees}deg)`;

      document.getElementById('digitalTime').title = `${now.toLocaleTimeString()}\n${Intl.DateTimeFormat().resolvedOptions().timeZone}\n${now.toDateString()}`;
    };

    const setupNavFade = () => {
      const header = document.querySelector('header');
      const player = document.querySelector('.video-container');
      if (!header || !player) return;

      let fadeTimeout;
      const showNav = () => {
        header.classList.remove('fade-out');
        clearTimeout(fadeTimeout);
        fadeTimeout = setTimeout(() => header.classList.add('fade-out'), 3000);
      };

      ['mousemove', 'scroll'].forEach((evt) => {
        document.addEventListener(evt, showNav);
      });

      showNav();
    };

    checkHealth();
    setInterval(checkHealth, 5000);
    checkDanger();
    setInterval(checkDanger, 5000);
    checkCaptions();
    setInterval(checkCaptions, 10000);
    checkDiscovery();
    setInterval(checkDiscovery, 60000);
    updateCoolClock();
    setInterval(updateCoolClock, 1000);
    setupNavFade();
  });
}

