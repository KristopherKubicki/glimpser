export function initPasswordToggle() {
  const setup = () => {
    const toggle = document.getElementById("password-toggle");
    const input = document.getElementById("password");
    if (!toggle || !input) return;
    const useEl = toggle.querySelector("use");
    const sprite = useEl ? useEl.getAttribute("href").split("#")[0] : "";
    toggle.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      if (useEl) {
        useEl.setAttribute("href", `${sprite}#${showing ? "eye" : "eye-off"}`);
      }
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
}

initPasswordToggle();
