export const NavState = {
  status: { level: null, title: '' },
  danger: { ready: false, title: '' },
  discover: { scanning: false }
};

let prevState = JSON.parse(JSON.stringify(NavState));

export function render() {
  const health = document.getElementById('health-status');
  if (
    health &&
    (NavState.status.level !== prevState.status.level ||
      NavState.status.title !== prevState.status.title)
  ) {
    health.classList.remove('status-healthy', 'status-degraded', 'status-error');
    if (NavState.status.level) {
      health.classList.add(`status-${NavState.status.level}`);
    }
    health.title = NavState.status.title;
  }

  const danger = document.getElementById('danger-status');
  if (
    danger &&
    (NavState.danger.ready !== prevState.danger.ready ||
      NavState.danger.title !== prevState.danger.title)
  ) {
    danger.classList.remove('danger-ready', 'danger-off');
    danger.classList.add(NavState.danger.ready ? 'danger-ready' : 'danger-off');
    danger.title = NavState.danger.title;
    danger.textContent = NavState.danger.ready ? '!' : '×';
  }

  const discover = document.getElementById('discover-link');
  if (discover && NavState.discover.scanning !== prevState.discover.scanning) {
    discover.classList.toggle('discover-scanning', NavState.discover.scanning);
  }

  prevState = JSON.parse(JSON.stringify(NavState));
}

export function setStatus(level, title) {
  NavState.status.level = level;
  NavState.status.title = title;
}

export function setDanger(ready, title) {
  NavState.danger.ready = ready;
  NavState.danger.title = title;
}

export function setDiscover(scanning) {
  NavState.discover.scanning = scanning;
}

export function initNav() {
  document.addEventListener('DOMContentLoaded', () => {
    function buildHealthTitle(data, prefix) {
      let title =
        `System Status: ${prefix}\n\n` +
        `CPU: ${data.metrics.cpu_usage}%\n` +
        `Memory: ${data.metrics.memory_usage}%\n` +
        `Disk: ${data.metrics.disk_usage}%\n` +
        `Open Files: ${data.metrics.open_files}\n` +
        `Threads: ${data.metrics.thread_count}\n` +
        `Uptime: ${data.metrics.uptime}\n`;
      if (data.error_messages && data.error_messages.length) {
        title += '\nErrors:\n' + data.error_messages.join('\n');
      }
      return title;
    }

    function checkHealth() {
      fetch('/health')
        .then((response) => response.json())
        .then((data) => {
          if (data.status === 'healthy') {
            setStatus('healthy', buildHealthTitle(data, 'Healthy'));
          } else {
            setStatus('degraded', buildHealthTitle(data, 'Degraded'));
          }
          render();
        })
        .catch((error) => {
          console.error('Error fetching health status:', error);
          setStatus('error', 'Error: Unable to fetch health status');
          render();
        });
    }

    function checkDanger() {
      fetch('/danger_status')
        .then((response) => response.json())
        .then((data) => {
          let title = 'Danger Mode Off';
          const reason = [];
          if (!data.port_open) reason.push('Debug port closed');
          if (!data.idle) reason.push('User active');
          if (data.ready) {
            title = 'Danger Mode Ready';
          } else if (reason.length) {
            title += '\n' + reason.join(', ');
          }
          setDanger(data.ready, title);
          render();
        })
        .catch((error) => {
          console.error('Error fetching danger status:', error);
        });
    }

    function updateCoolClock() {
      const now = new Date();
      const secondsDegrees = (now.getSeconds() / 60) * 360;
      const minutesDegrees =
        (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
      const hoursDegrees =
        (now.getHours() / 12) * 360 + (now.getMinutes() / 60) * 30;

      document.querySelector(
        '.second-hand'
      ).style.transform = `rotate(${secondsDegrees}deg)`;
      document.querySelector(
        '.minute-hand'
      ).style.transform = `rotate(${minutesDegrees}deg)`;
      document.querySelector(
        '.hour-hand'
      ).style.transform = `rotate(${hoursDegrees}deg)`;

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

    setInterval(checkHealth, 5000);
    checkHealth();

    setInterval(checkDanger, 5000);
    checkDanger();

    setInterval(updateCoolClock, 1000);
    updateCoolClock();

    setupNavFade();
  });
}
