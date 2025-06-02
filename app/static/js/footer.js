export function initFooterFade() {
  document.addEventListener('DOMContentLoaded', () => {
    const footer = document.querySelector('footer');
    if (!footer) return;

    let fadeTimeout;

    const showFooter = () => {
      footer.classList.remove('fade-out');
      clearTimeout(fadeTimeout);
      fadeTimeout = setTimeout(() => footer.classList.add('fade-out'), 3000);
    };

    ['mousemove', 'scroll'].forEach((evt) => {
      document.addEventListener(evt, showFooter);
    });

    showFooter();
  });
}
