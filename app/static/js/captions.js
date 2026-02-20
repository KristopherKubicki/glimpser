import { updateHumanizedTimes } from "./templates.js";
import { parseTimestamp } from "./time_utils.js";

function playTone(duration = 500) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  const ctx = new Ctx();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = 440;
  gain.gain.setValueAtTime(0.05, ctx.currentTime);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + duration / 1000);
  osc.onended = () => ctx.close();
}

export function initCaptions() {
  const run = () => {
    const supportsSpeech =
      "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
    const tabs = document.querySelectorAll(".tab-link");
    const contents = document.querySelectorAll(".tab-content");
    if (!tabs.length) return;

    const modal = document.getElementById("update-modal");
    const confirmBtn = document.getElementById("update-confirm");
    const cancelBtn = document.getElementById("update-cancel");
    const closeBtn = document.getElementById("update-close");
    let pending = null;

    const hide = () => {
      if (modal) modal.style.display = "none";
    };

    cancelBtn?.addEventListener("click", hide);
    closeBtn?.addEventListener("click", hide);
    confirmBtn?.addEventListener("click", () => {
      hide();
      if (pending) window.updateTemplate(pending);
    });

    const chatOpen = document.getElementById("chat-open");
    const chatModal = document.getElementById("chat-modal");
    const chatClose = document.getElementById("chat-close");
    const chatSubmit = document.getElementById("chat-submit");
    const chatQuestion = document.getElementById("chat-question");
    const chatAnswer = document.getElementById("chat-answer");

    chatOpen?.addEventListener("click", () => {
      if (chatModal) chatModal.style.display = "block";
      if (chatAnswer) chatAnswer.textContent = "";
      chatQuestion?.focus();
    });
    chatClose?.addEventListener("click", () => {
      if (chatModal) chatModal.style.display = "none";
    });
    chatSubmit?.addEventListener("click", async () => {
      if (!chatQuestion || !chatQuestion.value.trim()) return;
      if (chatAnswer) chatAnswer.textContent = "Thinking...";
      const start = document.getElementById("caption-start")?.value;
      const end = document.getElementById("caption-end")?.value;
      const resp = await fetch("/captions_chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: chatQuestion.value, start, end }),
      });
      const data = await resp.json();
      if (chatAnswer) {
        chatAnswer.textContent = data.truncated
          ? `${data.answer}\n(Input truncated)`
          : data.answer;
      }
      const table = document.querySelector("#captions-table tbody");
      if (table && data.answer) {
        const now = new Date().toISOString().replace("T", " ").slice(0, 19);
        const rowQ = document.createElement("tr");
        rowQ.innerHTML = `<td>${now}</td><td>Q: ${chatQuestion.value}</td>`;
        if (supportsSpeech) {
          const btn = document.createElement("button");
          btn.className = "play-caption";
          btn.title = "Play caption";
          btn.innerHTML = "&#9658;";
          btn.dataset.caption = `Q: ${chatQuestion.value}`;
          const cell = document.createElement("td");
          cell.appendChild(btn);
          rowQ.appendChild(cell);
        }

        const rowA = document.createElement("tr");
        rowA.innerHTML = `<td>${now}</td><td>A: ${data.answer}</td>`;
        if (supportsSpeech) {
          const btnA = document.createElement("button");
          btnA.className = "play-caption";
          btnA.title = "Play caption";
          btnA.innerHTML = "&#9658;";
          btnA.dataset.caption = `A: ${data.answer}`;
          const cellA = document.createElement("td");
          cellA.appendChild(btnA);
          rowA.appendChild(cellA);
        }
        table.prepend(rowA);
        table.prepend(rowQ);
      }
    });

    const captionsTable = document.getElementById("captions-table");
    if (supportsSpeech) {
      captionsTable?.addEventListener("click", (e) => {
        const btn = e.target.closest(".play-caption");
        if (!btn) return;
        const text = btn.dataset.caption;
        if (!text) return;
        window.speechSynthesis.cancel();
        playTone();
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
      });
    } else {
      document
        .querySelectorAll(".play-caption")
        .forEach((b) => b.classList.add("hidden"));
    }

    document.getElementById("camera-table")?.addEventListener("click", (e) => {
      const btn = e.target.closest(".update-button");
      if (!btn) return;
      e.preventDefault();
      pending = btn.dataset.template;
      if (modal) {
        modal.style.display = "block";
      } else {
        window.updateTemplate(pending);
      }
    });

    const captionTable = document.querySelector("#captions-table tbody");
    let activeBtn = null;
    let paused = false;
    if (!supportsSpeech) {
      document
        .querySelectorAll(".speech-btn, .play-caption")
        .forEach((b) => b.classList.add("hidden"));
    } else {
      captionTable?.addEventListener("click", (e) => {
        const btn = e.target.closest(".speech-btn");
        if (!btn) return;
        const text = btn
          .closest("td")
          ?.querySelector(".caption-text")?.textContent;
        if (!text) return;
        if (
          btn === activeBtn &&
          speechSynthesis.speaking &&
          !speechSynthesis.paused
        ) {
          speechSynthesis.pause();
          btn.textContent = "\u25B6";
          paused = true;
          return;
        }
        if (btn === activeBtn && paused) {
          speechSynthesis.resume();
          btn.textContent = "\u23F8";
          paused = false;
          return;
        }
        speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.onend = () => {
          if (activeBtn) activeBtn.textContent = "\u25B6";
          activeBtn = null;
          paused = false;
        };
        playTone();
        speechSynthesis.speak(utter);
        if (activeBtn) activeBtn.textContent = "\u25B6";
        activeBtn = btn;
        btn.textContent = "\u23F8";
        paused = false;
      });
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
      });
    });

    const radios = document.querySelectorAll("input[name='caption-field']");
    const header = document.querySelector("#camera-table th.view-header");
    const rows = document.querySelectorAll("#camera-table tbody tr");

    const applyView = (view) => {
      if (header) header.textContent = view === "prompt" ? "Prompt" : "Caption";
      rows.forEach((row) => {
        const prompt = row.querySelector(".chat-prompt");
        const response = row.querySelector(".chat-response");
        const cell = row.cells[1];
        if (!cell) return;
        if (prompt) prompt.classList.toggle("hidden", view !== "prompt");
        if (response) response.classList.toggle("hidden", view !== "caption");
        const val =
          view === "prompt"
            ? prompt?.querySelector("textarea")?.value || ""
            : response?.querySelector(".last-caption")?.textContent || "";
        cell.dataset.value = val.toLowerCase();
      });
      localStorage.setItem("captionView", view);
    };

    radios.forEach((r) => {
      r.addEventListener("change", () => applyView(r.value));
    });
    const stored = localStorage.getItem("captionView") || "caption";
    radios.forEach((r) => {
      r.checked = r.value === stored;
    });
    applyView(stored);

    const page = document.querySelector(".captions-page");
    const latest = page?.dataset.latestCaption || "";
    const chyron = document.getElementById("caption-chyron");
    const speed = chyron ? parseFloat(chyron.dataset.speed || "0") : 0;
    if (latest && speed > 0) {
      window.dispatchEvent(new CustomEvent("showChyron", { detail: latest }));
    }

    setupLiveHistoryUpdates();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
}

function setupLiveHistoryUpdates() {
  const tbody = document.querySelector("#captions-table tbody");
  const header = document.querySelector(
    "#captions-table th.sortable[data-type='date']",
  );
  if (!tbody || !header) return;

  let latest = tbody.querySelector("tr:not(.no-data) span[data-time]")?.dataset
    .time;

  const fetchLatest = async () => {
    if (header.dataset.order !== "desc") return;
    try {
      const resp = await fetch("/captions_status");
      const data = await resp.json();
      if (!data.timestamp || !data.caption) return;
      const dataTs = parseTimestamp(data.timestamp);
      const latestTs = parseTimestamp(latest);
      if (dataTs && (!latestTs || dataTs > latestTs)) {
        const row = document.createElement("tr");
        row.innerHTML = `<td><span class="humanized-time" data-time="${data.timestamp}">${data.timestamp}</span></td><td>${data.caption}</td>`;
        tbody.prepend(row);
        tbody.querySelector(".no-data")?.remove();
        latest = data.timestamp;
        updateHumanizedTimes();
      }
    } catch (err) {
      console.error("Error updating captions", err);
    }
  };

  fetchLatest();
  setInterval(fetchLatest, 10000);
}
