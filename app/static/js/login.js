export function initLogin() {
  document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    if (!form) return;
    form.addEventListener('submit', (e) => {
      const user = form.elements['username'].value.trim();
      const pass = form.elements['password'].value.trim();
      const error = document.getElementById('login-error');
      if (!user || !pass) {
        e.preventDefault();
        if (error) {
          error.textContent = 'Username and password are required.';
          error.classList.remove('hidden');
        }
      }
    });
  });
}

initLogin();
