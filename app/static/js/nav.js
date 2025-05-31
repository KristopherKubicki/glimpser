export function initNavToggle() {
  document.addEventListener('DOMContentLoaded', () => {
    const toggleButton = document.querySelector('.nav-toggle');
    const nav = document.querySelector('nav');
    if (toggleButton && nav) {
      toggleButton.addEventListener('click', () => {
        nav.classList.toggle('open');
      });
    }
  });
}
