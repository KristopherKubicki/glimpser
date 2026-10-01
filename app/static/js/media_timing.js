// Browser presentation rate, not a claim about the camera's configured FPS.
export function frameRateSample(previous, quality, now) {
  const total = Number(quality.totalVideoFrames);
  const dropped = Number(quality.droppedVideoFrames);
  const frames = total - dropped;
  if (![frames, now].every(Number.isFinite) || frames < 0)
    return { next: null, fps: null };
  const next = { frames, time: now };
  if (!previous || frames < previous.frames || now <= previous.time)
    return { next, fps: null };
  const elapsed = now - previous.time;
  if (elapsed < 500) return { next: previous, fps: null };
  return {
    next,
    fps: Math.round(((frames - previous.frames) * 10000) / elapsed) / 10,
  };
}
