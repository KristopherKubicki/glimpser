export function initUrlTester() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("url");
    const status = document.getElementById("url-status");
    if (!input || !status) return;

    let controller;
    const check = async () => {
      const url = input.value.trim();
      status.textContent = "";
      status.className = "url-status";
      if (!url) return;
      controller?.abort();
      controller = new AbortController();
      status.textContent = "…";
      try {
        const res = await fetch(
          `/templates/test_url?url=${encodeURIComponent(url)}`,
          {
            signal: controller.signal,
          },
        );
        const data = await res.json();
        if (res.ok && data.ok) {
          status.textContent = "✓";
          status.classList.add("ok");
        } else {
          status.textContent = "✗";
          status.classList.add("bad");
        }
      } catch {
        if (controller.signal.aborted) return;
        status.textContent = "✗";
        status.classList.add("bad");
      }
    };

    input.addEventListener("blur", check);
    input.addEventListener("change", check);
  });
}
