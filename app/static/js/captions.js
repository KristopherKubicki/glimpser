import { updateHumanizedTimes } from "./templates.js";

export function initCaptions() {
  document.addEventListener("DOMContentLoaded", () => {
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
        rowQ.innerHTML = `<td>${now}</td><td>Q: ${chatQuestion.value}</td><td><button class="play-caption" title="Play caption">&#9658;</button></td>`;
        rowQ.querySelector("button").dataset.caption =
          `Q: ${chatQuestion.value}`;
        const rowA = document.createElement("tr");
        rowA.innerHTML = `<td>${now}</td><td>A: ${data.answer}</td><td><button class="play-caption" title="Play caption">&#9658;</button></td>`;
        rowA.querySelector("button").dataset.caption = `A: ${data.answer}`;
        table.prepend(rowA);
        table.prepend(rowQ);
      }
    });

    const captionsTable = document.getElementById("captions-table");
    captionsTable?.addEventListener("click", (e) => {
      const btn = e.target.closest(".play-caption");
      if (!btn || !window.speechSynthesis) return;
      const text = btn.dataset.caption;
      if (!text) return;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    });

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
      speechSynthesis.speak(utter);
      if (activeBtn) activeBtn.textContent = "\u25B6";
      activeBtn = btn;
      btn.textContent = "\u23F8";
      paused = false;
    });

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
      });
    });

    const page = document.querySelector(".captions-page");
    const latest = page?.dataset.latestCaption || "";
    const chyron = document.getElementById("caption-chyron");
    const speed = chyron ? parseFloat(chyron.dataset.speed || "0") : 0;
    if (latest && speed > 0) {
      window.dispatchEvent(new CustomEvent("showChyron", { detail: latest }));
    }

    setupLiveHistoryUpdates();
  });
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
      if (!latest || new Date(data.timestamp) > new Date(latest)) {
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
