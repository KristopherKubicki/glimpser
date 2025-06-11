export function initTooltips() {
  document.addEventListener("DOMContentLoaded", () => {
    const tooltip = document.createElement("div");
    tooltip.className = "dynamic-tooltip hidden";
    document.body.appendChild(tooltip);

    const moveTooltip = (e) => {
      const offset = 10;
      const tooltipWidth = tooltip.offsetWidth;
      const tooltipHeight = tooltip.offsetHeight;

      const x = e.pageX ?? e.clientX;
      const y = e.pageY ?? e.clientY;

      let left = x + offset;
      if (left + tooltipWidth > window.innerWidth) {
        left = x - tooltipWidth - offset;
      }

      let top = y + offset;
      const viewportBottom = window.scrollY + window.innerHeight;
      if (top + tooltipHeight > viewportBottom) {
        top = y - tooltipHeight - offset;
      }
      if (top < window.scrollY) {
        top = window.scrollY;
      }

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    };

    const showTooltip = (e) => {
      const target = e.target.closest("[title]");
      if (!target) return;
      const text = target.getAttribute("title");
      if (!text) return;
      target.setAttribute("data-title", text);
      target.removeAttribute("title");
      tooltip.textContent = text;
      moveTooltip(e);
      tooltip.classList.remove("hidden");
      target.addEventListener("mousemove", moveTooltip);
    };

    const hideTooltip = (e) => {
      tooltip.classList.add("hidden");
      e.target.removeEventListener("mousemove", moveTooltip);
      const orig = e.target.getAttribute("data-title");
      if (orig) {
        e.target.setAttribute("title", orig);
        e.target.removeAttribute("data-title");
      }
    };

    document.addEventListener("mouseover", showTooltip);
    document.addEventListener("focusin", showTooltip);
    document.addEventListener("mouseout", hideTooltip);
    document.addEventListener("focusout", hideTooltip);
  });
}
