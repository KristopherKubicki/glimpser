import { mountMotionPreview } from "./motion_preview.js";

export function createPriorityAlert(event, duration, onFinish) {
  const activityLabels = {
    doorbell: "DOORBELL RANG",
    person: "PERSON DETECTED",
    motion: "MOTION DETECTED",
  };
  const activity = activityLabels[event.kind] || activityLabels.motion;
  const node = document.createElement("section");
  node.className = "landing-priority-notice kiosk-priority-alert";
  node.setAttribute("role", "status");
  node.setAttribute(
    "aria-label",
    event.kind === "arrival"
      ? `${event.subject_label} arrived`
      : `${activity.toLowerCase()} at ${event.camera_name || "priority camera"}`,
  );
  const label = document.createElement("div");
  label.className = "kiosk-priority-label";
  label.textContent = event.kind === "arrival" ? "ARRIVAL CONFIRMED" : activity;
  const camera = document.createElement("strong");
  camera.textContent =
    event.kind === "arrival"
      ? `${event.subject_label} arrived`
      : event.camera_name || "Priority camera";
  const footer = document.createElement("div");
  footer.className = "kiosk-priority-footer";
  const remaining = document.createElement("span");
  // Avoid announcing every tick to screen readers.
  remaining.setAttribute("aria-hidden", "true");
  const resume = document.createElement("button");
  resume.type = "button";
  resume.textContent = "Resume rotation";
  let deadline = Date.now() + duration;
  let finished = false;
  let timer;
  let replay = null;
  const finish = () => {
    if (finished) return;
    finished = true;
    window.clearInterval(timer);
    replay?.dispose();
    onFinish();
  };
  resume.addEventListener("click", finish);
  const update = () => {
    const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    remaining.textContent = `Returning in ${seconds}s`;
    if (!seconds) finish();
  };
  footer.append(remaining, resume);
  node.append(label, camera, footer);
  if (event.replay_available && event.camera_name) {
    node.classList.add("has-replay");
    replay = mountMotionPreview(event.camera_name, node, {
      autoCloseMs: duration,
    });
  }
  update();
  timer = window.setInterval(update, 1000);
  return {
    node,
    holdLive(durationMs) {
      if (finished) return;
      deadline = Date.now() + durationMs;
      replay?.dispose();
      replay = null;
      node.classList.remove("has-replay");
      update();
    },
    dispose() {
      finished = true;
      window.clearInterval(timer);
      replay?.dispose();
      node.remove();
    },
  };
}
