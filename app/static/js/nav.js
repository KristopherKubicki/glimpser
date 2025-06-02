export function initNav() {
  document.addEventListener('DOMContentLoaded', () => {
    const healthStatus = document.getElementById('health-status');
    const dangerStatus = document.getElementById('danger-status');
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
    updateCoolClock();
    setInterval(updateCoolClock, 1000);
    setupNavFade();
  });
}

