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
    const chatHistory = document.getElementById("chat-history");

    const closeChat = () => {
      if (chatModal) chatModal.style.display = "none";
    };

    chatOpen?.addEventListener("click", () => {
      if (chatModal) {
        chatModal.style.display = "block";
        if (chatQuestion) {
          chatQuestion.value = "";
          chatQuestion.focus();
        }
      }
    });
    chatClose?.addEventListener("click", closeChat);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && chatModal?.style.display === "block") {
        closeChat();
      }
    });

    const sendQuestion = async () => {
      if (!chatQuestion || !chatQuestion.value.trim()) return;
      const start = document.getElementById("caption-start")?.value;
      const end = document.getElementById("caption-end")?.value;
      if (chatAnswer) chatAnswer.textContent = "Thinking...";
      try {
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
        if (chatHistory) {
          const q = document.createElement("div");
          q.textContent = `Q: ${chatQuestion.value}`;
          const a = document.createElement("div");
          a.textContent = `A: ${data.answer}`;
          chatHistory.append(q, a);
        }
        const table = document.querySelector("#captions-table tbody");
        if (table && data.answer) {
          const now = new Date().toISOString().replace("T", " ").slice(0, 19);
          const rowQ = document.createElement("tr");
          const qTime = document.createElement("td");
          qTime.textContent = now;
          const qText = document.createElement("td");
          qText.textContent = `Q: ${chatQuestion.value}`;
          rowQ.append(qTime, qText);
          const rowA = document.createElement("tr");
          const aTime = document.createElement("td");
          aTime.textContent = now;
          const aText = document.createElement("td");
          aText.textContent = `A: ${data.answer}`;
          rowA.append(aTime, aText);
          table.prepend(rowA);
          table.prepend(rowQ);
        }
      } catch (err) {
        if (chatAnswer) chatAnswer.textContent = "Unable to reach server";
      }
    };

    chatSubmit?.addEventListener("click", sendQuestion);
    chatQuestion?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
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
