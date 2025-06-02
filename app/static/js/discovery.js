import { fetchJson } from './fetch_utils.js';

export function initDiscoveryToggle() {
  document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('toggle-discovery');
    const statusSpan = document.getElementById('discovery-bg-status');
    if (!toggleBtn || !statusSpan) return;

    toggleBtn.addEventListener('click', async () => {
      const confirmToggle = confirm(
        `Are you sure you want to ${
          toggleBtn.textContent.includes('Stop') ? 'stop' : 'start'
        } background discovery?`
      );
      if (!confirmToggle) return;
      try {
        const data = await fetchJson('/toggle_discovery', { method: 'POST' });
        statusSpan.textContent = data.status;
        toggleBtn.textContent =
          data.status === 'running' ? 'Stop Discovery' : 'Start Discovery';
      } catch (err) {
        statusSpan.textContent = 'error';
        alert('Unable to toggle discovery.');
      }
    });

    fetchJson('/discovery_status')
      .then((data) => {
        statusSpan.textContent = data.status;
        toggleBtn.textContent =
          data.status === 'running' ? 'Stop Discovery' : 'Start Discovery';
      })
      .catch(() => {
        statusSpan.textContent = 'error';
      });
  });
}
