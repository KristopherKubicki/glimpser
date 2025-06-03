export function initTooltips() {
  document.addEventListener("DOMContentLoaded", () => {
    const tooltip = document.createElement("div");
    tooltip.className = "dynamic-tooltip hidden";
    document.body.appendChild(tooltip);

    const moveTooltip = (e) => {
      tooltip.style.left = `${e.pageX + 10}px`;
      tooltip.style.top = `${e.pageY + 10}px`;
    };

    const showTooltip = (e) => {
      const target = e.target.closest("[title]");
      if (!target) return;
      const text = target.getAttribute("title");
      if (!text) return;
      tooltip.textContent = text;
      moveTooltip(e);
      tooltip.classList.remove("hidden");
      target.addEventListener("mousemove", moveTooltip);
    };

    const hideTooltip = (e) => {
      tooltip.classList.add("hidden");
      e.target.removeEventListener("mousemove", moveTooltip);
    };

    document.addEventListener("mouseover", showTooltip);
    document.addEventListener("focusin", showTooltip);
    document.addEventListener("mouseout", hideTooltip);
    document.addEventListener("focusout", hideTooltip);
  });
}
