import { pollingFetch } from './polling.js';

export function initNav() {
  document.addEventListener('DOMContentLoaded', () => {
    function renderHealth(data) {
      const healthStatus = document.getElementById('health-status');
      if (!healthStatus || !data) return;
      if (data.status === 'healthy') {
        healthStatus.style.backgroundColor = 'green';
        healthStatus.title = 'System Status: Healthy\n\n';
      } else {
        healthStatus.style.backgroundColor = 'red';
        healthStatus.title = 'System Status: Degraded\n\n';
      }
      healthStatus.title += `CPU: ${data.metrics.cpu_usage}%\n` +
        `Memory: ${data.metrics.memory_usage}%\n` +
        `Disk: ${data.metrics.disk_usage}%\n` +
        `Open Files: ${data.metrics.open_files}\n` +
        `Threads: ${data.metrics.thread_count}\n` +
        `Uptime: ${data.metrics.uptime}\n`;

      if (data.error_messages && data.error_messages.length > 0) {
        healthStatus.title += '\nErrors:\n' + data.error_messages.join('\n');
      }
    }

    function renderHealthError() {
      const healthStatus = document.getElementById('health-status');
      if (healthStatus) {
        healthStatus.style.backgroundColor = 'red';
        healthStatus.title = 'Error: Unable to fetch health status';
      }
    }

    function renderDanger(data) {
      const dangerStatus = document.getElementById('danger-status');
      if (!dangerStatus || !data) return;
      if (data.ready) {
        dangerStatus.style.backgroundColor = 'orange';
        dangerStatus.textContent = '!';
        dangerStatus.title = 'Danger Mode Ready';
      } else {
        dangerStatus.style.backgroundColor = 'grey';
        dangerStatus.textContent = '×';
        let reason = [];
        if (!data.port_open) reason.push('Debug port closed');
        if (!data.idle) reason.push('User active');
        dangerStatus.title = 'Danger Mode Off';
        if (reason.length) dangerStatus.title += '\n' + reason.join(', ');
      }
    }

    function renderDangerError() {
      console.error('Error fetching danger status');
    }

    function updateCoolClock() {
      const now = new Date();
      const secondsDegrees = (now.getSeconds() / 60) * 360;
      const minutesDegrees = (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
      const hoursDegrees = (now.getHours() / 12) * 360 + (now.getMinutes() / 60) * 30;

      document.querySelector('.second-hand').style.transform = `rotate(${secondsDegrees}deg)`;
      document.querySelector('.minute-hand').style.transform = `rotate(${minutesDegrees}deg)`;
      document.querySelector('.hour-hand').style.transform = `rotate(${hoursDegrees}deg)`;

      document.getElementById('digitalTime').title =
        `${now.toLocaleTimeString()}\n${Intl.DateTimeFormat().resolvedOptions().timeZone}\n${now.toDateString()}`;
    }

    function setupNavFade() {
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
    }

    (async () => {
      for await (const data of pollingFetch(
        () => fetch('/health').then((r) => r.json()),
        5000,
      )) {
        if (data) renderHealth(data);
        else renderHealthError();
      }
    })();

    (async () => {
      for await (const data of pollingFetch(
        () => fetch('/danger_status').then((r) => r.json()),
        5000,
      )) {
        if (data) renderDanger(data);
        else renderDangerError();
      }
    })();

    setInterval(updateCoolClock, 1000);
    updateCoolClock();

    setupNavFade();
  });
}
