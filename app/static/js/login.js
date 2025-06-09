export function initLogin() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("login-form");
    const noteEl = document.getElementById("security-note");
    if (!form) return;
    if (noteEl) {
      if (location.protocol === "https:") {
        noteEl.textContent = "Your credentials are encrypted in transit.";
      } else {
        noteEl.textContent =
          "Warning: credentials sent over HTTP are not secure.";
        noteEl.classList.add("warning");
      }
    }
    form.addEventListener("submit", (e) => {
      const user = form.elements["username"].value.trim();
      const pass = form.elements["password"].value.trim();
      const error = document.getElementById("login-error");
      if (!user || !pass) {
        e.preventDefault();
        if (error) {
          error.textContent = "Username and password are required.";
          error.classList.remove("hidden");
        }
      }
    });
  });
}

initLogin();
