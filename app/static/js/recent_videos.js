export function initRecentVideosModal(list, camera) {
  const collator = new Intl.Collator(undefined, {
    numeric: true,
    sensitivity: "base",
  });
  const items = Array.from(list || []);
  const lastIndex = items.indexOf("last_video.mp4");
  if (lastIndex !== -1) items.splice(lastIndex, 1);
  items.sort((a, b) => collator.compare(a, b));
  if (lastIndex !== -1) items.push("last_video.mp4");

  let index = 0;
  const video = document.getElementById("live-video");
  const source = video?.querySelector("source");
  const prev = document.getElementById("prev-clip-btn");
  const next = document.getElementById("next-clip-btn");

  function updateButtons() {
    if (prev) prev.disabled = index <= 0;
    if (next) {
      if (index >= items.length - 1) {
        next.classList.add("go-live");
        next.textContent = "Live";
        next.disabled = false;
      } else {
        next.classList.remove("go-live");
        next.textContent = "\u25B6";
        next.disabled = false;
      }
    }
  }

  function loadClip(i) {
    if (i < 0 || i >= items.length) return;
    index = i;
    const file = items[i];
    if (file === "last_video.mp4") {
      if (source) source.src = `/last_video/${camera}`;
    } else if (source) {
      source.src = `/videos/${camera}/${file}`;
    }
    video.removeAttribute("data-hd-src");
    video.load();
    updateButtons();
  }

  prev?.addEventListener("click", () => {
    prev.classList.add("clicked");
    setTimeout(() => prev.classList.remove("clicked"), 150);
    loadClip(index - 1);
  });

  next?.addEventListener("click", () => {
    next.classList.add("clicked");
    setTimeout(() => next.classList.remove("clicked"), 150);
    if (index >= items.length - 1) {
      window.location.href = `/live?camera=${camera}`;
    } else {
      loadClip(index + 1);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (
      e.target instanceof HTMLInputElement ||
      e.target instanceof HTMLTextAreaElement
    )
      return;
    if (e.key === "ArrowLeft") {
      loadClip(index - 1);
    } else if (e.key === "ArrowRight") {
      if (index >= items.length - 1) {
        window.location.href = `/live?camera=${camera}`;
      } else {
        loadClip(index + 1);
      }
    }
  });

  document.querySelectorAll("#videos-modal video").forEach((vid) => {
    vid.addEventListener("click", () => {
      const file = vid.dataset.file;
      const i = items.indexOf(file);
      if (i !== -1) loadClip(i);
      if (typeof window.closeGenericModal === "function") {
        window.closeGenericModal("videos-modal");
      }
    });
  });

  updateButtons();
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.recentVideos && window.currentCamera) {
    initRecentVideosModal(window.recentVideos, window.currentCamera);
  }
});
