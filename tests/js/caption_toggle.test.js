import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list">
    <div class="caption-overlay"></div>
  </div>
  <input id="grid-width-slider" type="range" value="160">
  <button id="caption-toggle"></button>
`;

let initTemplates;
let applyCaptionVisibility;
let setCaptionsVisibility;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  initTemplates = mod.initTemplates;
  applyCaptionVisibility = mod.applyCaptionVisibility;
  setCaptionsVisibility = mod.setCaptionsVisibility;
});

describe("caption toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.getElementById("caption-toggle").className = "";
    document.documentElement.classList.remove("hide-captions");
  });

  test("button disabled when tiles small", () => {
    applyCaptionVisibility(100);
    const btn = document.getElementById("caption-toggle");
    expect(btn.classList.contains("disabled")).toBe(true);
    expect(btn.title).toMatch(/increase tile size/i);
  });

  test("click toggles visibility", () => {
    initTemplates();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const btn = document.getElementById("caption-toggle");
    applyCaptionVisibility(200);
    btn.click();
    expect(document.documentElement.classList.contains("hide-captions")).toBe(
      true,
    );
    expect(btn.classList.contains("active")).toBe(false);
    btn.click();
    expect(document.documentElement.classList.contains("hide-captions")).toBe(
      false,
    );
    expect(btn.classList.contains("active")).toBe(true);
  });

  test("setCaptionsVisibility hides captions", () => {
    setCaptionsVisibility(false);
    expect(document.documentElement.classList.contains("hide-captions")).toBe(
      true,
    );
  });
});
