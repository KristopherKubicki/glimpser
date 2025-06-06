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
    });
    chatClose?.addEventListener("click", () => {
      if (chatModal) chatModal.style.display = "none";
    });
    chatSubmit?.addEventListener("click", async () => {
      if (!chatQuestion || !chatQuestion.value) return;
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

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
      });
    });
  });
}
