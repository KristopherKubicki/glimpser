import { jest } from "@jest/globals";

const html = `
  <div id="status-legend">
    <span class="status-item" data-status="recent"><span class="status-box recent"></span>Recent</span>
    <span class="status-item" data-status="error"><span class="status-box error"></span>Error</span>
  </div>
  <div id="template-list">
    <div class="templateDiv"><div class="video-container recent-screenshot"></div></div>
    <div class="templateDiv"><div class="video-container template-error"></div></div>
    <div class="templateDiv"><div class="video-container"></div></div>
  </div>
`;

document.body.innerHTML = html;

let setupStatusFilter;
let applyStatusFilter;
let updateStatusCounts;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  setupStatusFilter = mod.setupStatusFilter;
  applyStatusFilter = mod.applyStatusFilter;
  updateStatusCounts = mod.updateStatusCounts;
});

describe("status legend filter", () => {
  beforeEach(() => {
    document.body.innerHTML = html;
  });

  test("updateStatusCounts disables entries with no matches", () => {
    document
      .querySelectorAll(".video-container")
      .forEach((c) => (c.className = "video-container"));
    updateStatusCounts();
    const recent = document.querySelector('[data-status="recent"]');
    const error = document.querySelector('[data-status="error"]');
    expect(recent.classList.contains("disabled")).toBe(true);
    expect(error.classList.contains("disabled")).toBe(true);
  });

  test("click filters visible templates", () => {
    setupStatusFilter();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const recentItem = document.querySelector('[data-status="recent"]');
    recentItem.click();
    const visible = Array.from(
      document.querySelectorAll(".templateDiv"),
    ).filter((d) => d.style.display !== "none");
    expect(visible).toHaveLength(1);
    expect(visible[0].querySelector(".recent-screenshot")).not.toBeNull();
  });
});
