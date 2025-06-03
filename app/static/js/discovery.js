import { fetchJson } from './fetch_utils.js';

export function initDiscoveryToggle() {
  document.addEventListener('DOMContentLoaded', () => {
    const stopBtn = document.getElementById('stop-discovery');
    const statusSpan = document.getElementById('discovery-bg-status');
    if (!statusSpan) return;

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

    if (stopBtn) {
      stopBtn.addEventListener('click', async () => {
        const confirmStop = confirm(
          'Are you sure you want to stop background discovery?'
        );
        if (!confirmStop) return;
        try {
          const data = await fetchJson('/toggle_discovery', { method: 'POST' });
          statusSpan.textContent = formatStatus(data);
          stopBtn.style.display = data.status === 'running' ? 'inline-block' : 'none';
        } catch (err) {
          statusSpan.textContent = 'error';
          alert('Unable to stop discovery.');
        }
      });
    }

    fetchJson('/discovery_status')
      .then((data) => {
        statusSpan.textContent = formatStatus(data);
        if (stopBtn) {
          stopBtn.style.display = data.status === 'running' ? 'inline-block' : 'none';
        }
      })
      .catch(() => {
        statusSpan.textContent = 'error';
      });
  });
}
