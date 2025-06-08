export function initCliHelp() {
  document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("load-cli-help");
    const output = document.getElementById("cli-help");
    if (!button || !output) return;

    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const res = await fetch("/cli_help");
        output.textContent = await res.text();
      } catch (err) {
        output.textContent = "Failed to load help.";
        console.error(err);
      } finally {
        output.classList.remove("hidden");
      }
    });
  });
}
