import { fetchJson } from './fetch_utils.js';

export function initDiscoveryToggle() {
  document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('toggle-discovery');
    const statusSpan = document.getElementById('discovery-bg-status');
    if (!toggleBtn || !statusSpan) return;

    const minutes = (s) => `${Math.round(s / 60)}m`;
    const formatStatus = (d) => {
      let text = d.status;
      if (d.running_for) {
        text += ` (${minutes(d.running_for)})`;
      } else if (Number.isFinite(d.age) && d.status !== 'none') {
        text += ` (${minutes(d.age)} ago)`;
      }
      if (d.next_run_in) {
        text += `, next in ${minutes(d.next_run_in)}`;
      }
      return text;
    };

    toggleBtn.addEventListener('click', async () => {
      const confirmToggle = confirm(
        `Are you sure you want to ${
          toggleBtn.textContent.includes('Stop') ? 'stop' : 'start'
        } background discovery?`
      );
      if (!confirmToggle) return;
      try {
        const data = await fetchJson('/toggle_discovery', { method: 'POST' });
        statusSpan.textContent = formatStatus(data);
        toggleBtn.textContent =
          data.status === 'running' ? 'Stop Discovery' : 'Start Discovery';
      } catch (err) {
        statusSpan.textContent = 'error';
        alert('Unable to toggle discovery.');
      }
    });

    fetchJson('/discovery_status')
      .then((data) => {
        statusSpan.textContent = formatStatus(data);
        toggleBtn.textContent =
          data.status === 'running' ? 'Stop Discovery' : 'Start Discovery';
      })
      .catch(() => {
        statusSpan.textContent = 'error';
      });
  });
}
