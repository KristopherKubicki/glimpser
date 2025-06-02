export function initErrorHandling() {
  document.addEventListener('DOMContentLoaded', () => {
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);

    const queue = [];

    function renderQueue() {
      container.innerHTML = '';
      queue.forEach((item) => {
        const div = document.createElement('div');
        div.className = 'toast';
        div.textContent = item.message;
        container.appendChild(div);
      });
    }

    function addMessage(message) {
      const id = Date.now() + Math.random();
      queue.push({ id, message });
      renderQueue();
      setTimeout(() => {
        const index = queue.findIndex((i) => i.id === id);
        if (index !== -1) {
          queue.splice(index, 1);
          renderQueue();
        }
      }, 10000);
    }

    function handleError(event) {
      let msg = 'An error occurred';
      if (event.message) {
        msg = event.message;
      } else if (event.reason) {
        msg = event.reason.message || String(event.reason);
      }
      console.error('Captured error:', event);
      addMessage(msg);
    }

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleError);
  });
}
