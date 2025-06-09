export function initLogin() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("login-form");
    const noteEl = document.getElementById("security-note");
    attemptAutoLogin();
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
      const remember = form.elements["remember"].checked;
      const error = document.getElementById("login-error");
      if (!user || !pass) {
        e.preventDefault();
        if (error) {
          error.textContent = "Username and password are required.";
          error.classList.remove("hidden");
        }
        return;
      }
      if (remember) {
        localStorage.setItem(
          "autoLogin",
          JSON.stringify({ username: user, password: pass }),
        );
      } else {
        localStorage.removeItem("autoLogin");
      }
    });
  });
}

export async function attemptAutoLogin() {
  if (window.IS_LOGGED_IN) return false;
  const stored = localStorage.getItem("autoLogin");
  if (!stored) return false;
  try {
    const creds = JSON.parse(stored);
    const resp = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        username: creds.username,
        password: creds.password,
        remember: "on",
      }),
    });
    if (resp.redirected || resp.url.endsWith("/")) {
      window.IS_LOGGED_IN = true;
      if (window.location.pathname === "/login") {
        window.location.href = "/";
      }
      return true;
    }
  } catch (err) {
    console.error("Auto login failed", err);
  }
  return false;
}

initLogin();
