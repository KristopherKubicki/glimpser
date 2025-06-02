export function initSchedulerToggle() {
  document.addEventListener('DOMContentLoaded', () => {
    const toggleSchedulerButton = document.getElementById('toggle-scheduler');
    const schedulerStatus = document.getElementById('scheduler-status');
    if (toggleSchedulerButton && schedulerStatus) {
      toggleSchedulerButton.addEventListener('click', () => {
        const shouldToggle = confirm(
          `Are you sure you want to ${
            toggleSchedulerButton.textContent.includes('Stop') ? 'stop' : 'start'
          } the scheduler?`
        );
        if (!shouldToggle) return;
        fetch('/toggle_scheduler', { method: 'POST' })
          .then((res) => res.json())
          .then((data) => {
            schedulerStatus.textContent = data.status;
            toggleSchedulerButton.textContent =
              data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
          })
          .catch((error) => {
            console.error('Error:', error);
            schedulerStatus.textContent = 'Error occurred';
          });
      });

      fetch('/scheduler_status')
        .then((res) => res.json())
        .then((data) => {
          schedulerStatus.textContent = data.status;
          toggleSchedulerButton.textContent =
            data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
        })
        .catch((error) => {
          console.error('Error:', error);
          schedulerStatus.textContent = 'Error occurred';
        });
    }
  });
}
