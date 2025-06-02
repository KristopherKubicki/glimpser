export async function* pollingFetch(fetchFn, interval = 5000) {
  let lastFrame = performance.now();
  while (true) {
    if (!document.hidden) {
      try {
        yield await fetchFn();
      } catch (e) {
        console.error('Polling error:', e);
        yield undefined;
      }
    }
    await new Promise(r => setTimeout(r, interval));
    const before = performance.now();
    await new Promise(requestAnimationFrame);
    const after = performance.now();
    if (document.hidden || after - before > 33) {
      while (document.hidden || after - before > 33) {
        await new Promise(requestAnimationFrame);
        const now = performance.now();
        if (!document.hidden && now - after <= 33) break;
      }
    }
    lastFrame = performance.now();
  }
}
