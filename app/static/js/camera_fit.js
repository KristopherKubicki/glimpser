// Fill small aspect-ratio gaps without stretching or cropping away large edges.
export function cameraObjectFit(width, height, boxWidth, boxHeight) {
  if (
    ![width, height, boxWidth, boxHeight].every(
      (n) => Number.isFinite(n) && n > 0,
    )
  )
    return "contain";
  const source = width / height;
  const target = boxWidth / boxHeight;
  const retained = Math.min(source / target, target / source);
  return retained >= 0.92 ? "cover" : "contain";
}

export function fitCameraMedia(media, host, enabled) {
  if (!enabled || !host) {
    media.style.removeProperty("object-fit");
    return;
  }
  const bounds = host.getBoundingClientRect();
  media.style.objectFit = cameraObjectFit(
    media.videoWidth || media.naturalWidth,
    media.videoHeight || media.naturalHeight,
    bounds.width,
    bounds.height,
  );
}
