export function initClocks() {
  const clocks = document.querySelectorAll('.cool-clock');
  if (!clocks.length) return;

  const update = () => {
    const now = new Date();
    clocks.forEach((clock) => {
      const digital = clock.dataset.digital === 'true';
      const secondHand = clock.querySelector('.second-hand');
      const minuteHand = clock.querySelector('.minute-hand');
      const hourHand = clock.querySelector('.hour-hand');
      const digitalDisp = clock.querySelector('.digital-clock');
      if (digital) {
        if (digitalDisp) {
          digitalDisp.textContent = now.toLocaleTimeString();
        }
        if (secondHand) secondHand.style.display = 'none';
        if (minuteHand) minuteHand.style.display = 'none';
        if (hourHand) hourHand.style.display = 'none';
      } else {
        const secDeg = (now.getSeconds() / 60) * 360;
        const minDeg = (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
        const hourDeg = (now.getHours() / 12) * 360 + (now.getMinutes() / 60) * 30;
        if (secondHand) {
          secondHand.style.display = '';
          secondHand.style.transform = `rotate(${secDeg}deg)`;
        }
        if (minuteHand) {
          minuteHand.style.display = '';
          minuteHand.style.transform = `rotate(${minDeg}deg)`;
        }
        if (hourHand) {
          hourHand.style.display = '';
          hourHand.style.transform = `rotate(${hourDeg}deg)`;
        }
        if (digitalDisp) digitalDisp.textContent = '';
      }
    });
  };

  update();
  setInterval(update, 1000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initClocks);
} else {
  initClocks();
}
