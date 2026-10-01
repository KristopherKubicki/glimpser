function qs(id) {
  return document.getElementById(id);
}

function renderCandidates(candidates) {
  const results = qs("recovery-results");
  results.innerHTML = "";
  if (!candidates.length) {
    results.textContent =
      "No candidates found. Try re-rolling or refine the description.";
    return;
  }
  candidates.forEach((cand, idx) => {
    const row = document.createElement("div");
    row.className = "modal-row";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "recovery-candidate";
    radio.value = cand.url;
    radio.id = `recovery-candidate-${idx}`;
    const label = document.createElement("label");
    label.htmlFor = radio.id;
    label.textContent = cand.title || cand.url;

    const meta = document.createElement("div");
    meta.className = "modal-meta";
    meta.textContent = cand.notes || cand.source || "";

    const actions = document.createElement("div");
    actions.className = "form-actions";
    const previewBtn = document.createElement("button");
    previewBtn.type = "button";
    previewBtn.textContent = "Preview";
    previewBtn.addEventListener("click", () => previewCandidate(cand.url));

    const openLink = document.createElement("a");
    openLink.href = cand.url;
    openLink.target = "_blank";
    openLink.rel = "noreferrer";
    openLink.textContent = "Open";

    actions.appendChild(previewBtn);
    actions.appendChild(openLink);

    row.appendChild(radio);
    row.appendChild(label);
    row.appendChild(meta);
    row.appendChild(actions);
    results.appendChild(row);
  });
}

function setPreviewStatus(msg) {
  const status = qs("recovery-preview-status");
  if (!status) return;
  status.textContent = msg || "";
  status.style.display = msg ? "block" : "none";
}

async function previewCandidate(url) {
  const img = qs("recovery-preview-image");
  const video = qs("recovery-preview-video");
  setPreviewStatus("Generating preview...");
  try {
    const res = await fetch("/recovery/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        template_name: window.currentCamera,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setPreviewStatus(data.error || "Preview failed");
      return;
    }
    const previewType = data.preview_type || "image";
    if (previewType === "video" && video) {
      const source = video.querySelector("source");
      if (source) {
        source.src = `${data.preview_url}?t=${Date.now()}`;
      }
      video.classList.remove("hidden");
      video.load();
      video.play().catch(() => {});
      if (img) img.classList.add("hidden");
    } else if (img) {
      img.src = `${data.preview_url}?t=${Date.now()}`;
      img.classList.remove("hidden");
      if (video) {
        video.pause();
        video.classList.add("hidden");
      }
    }
    setPreviewStatus("");
  } catch {
    setPreviewStatus("Preview failed");
  }
}

async function runSearch({ reroll = false } = {}) {
  const desc = qs("recovery-description");
  const searchBtn = qs("recovery-search");
  const rerollBtn = qs("recovery-reroll");
  const applyBtn = qs("recovery-apply");
  const results = qs("recovery-results");
  const selectedBefore = document.querySelector(
    "input[name='recovery-candidate']:checked",
  );
  const exclude = new Set(window.recoveryExclude || []);
  if (reroll && selectedBefore) exclude.add(selectedBefore.value);
  if (window.recoveryCandidates) {
    window.recoveryCandidates.forEach((cand) => exclude.add(cand.url));
  }

  if (results) results.textContent = "Searching...";
  if (searchBtn) searchBtn.disabled = true;
  if (rerollBtn) rerollBtn.disabled = true;
  if (applyBtn) applyBtn.disabled = true;

  try {
    const res = await fetch(`/recovery/search/${window.currentCamera}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description: desc ? desc.value : "",
        exclude_urls: Array.from(exclude),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (results) results.textContent = "Recovery search failed.";
      return;
    }
    window.recoveryCandidates = data.candidates || [];
    window.recoveryExclude = Array.from(exclude);
    renderCandidates(window.recoveryCandidates);
    if (rerollBtn) rerollBtn.disabled = window.recoveryCandidates.length === 0;
  } catch {
    if (results) results.textContent = "Recovery search failed.";
  } finally {
    if (searchBtn) searchBtn.disabled = false;
  }
}

async function applySelected() {
  const selected = document.querySelector(
    "input[name='recovery-candidate']:checked",
  );
  if (!selected) return;
  const url = selected.value;
  if (!confirm("Apply this URL to the camera?")) return;
  const applyBtn = qs("recovery-apply");
  if (applyBtn) applyBtn.disabled = true;
  try {
    const res = await fetch(`/recovery/apply/${window.currentCamera}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert("Apply failed.");
      return;
    }
    window.location.reload();
  } catch {
    alert("Apply failed.");
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

window.openRecoveryModal = function openRecoveryModal() {
  const modal = qs("recovery-modal");
  if (!modal) return;
  modal.style.display = "block";
  const desc = qs("recovery-description");
  if (desc && !desc.value) {
    const notes = window.templateDetails?.[window.currentCamera]?.notes || "";
    desc.value = notes;
  }
  const img = qs("recovery-preview-image");
  const video = qs("recovery-preview-video");
  if (img) img.classList.remove("hidden");
  if (video) {
    video.pause();
    video.classList.add("hidden");
  }
};

document.addEventListener("DOMContentLoaded", () => {
  const searchBtn = qs("recovery-search");
  const rerollBtn = qs("recovery-reroll");
  const applyBtn = qs("recovery-apply");
  if (searchBtn) searchBtn.addEventListener("click", () => runSearch());
  if (rerollBtn)
    rerollBtn.addEventListener("click", () => runSearch({ reroll: true }));
  if (applyBtn) applyBtn.addEventListener("click", applySelected);

  document.addEventListener("change", (evt) => {
    if (evt.target && evt.target.name === "recovery-candidate") {
      if (applyBtn) applyBtn.disabled = false;
    }
  });
});
