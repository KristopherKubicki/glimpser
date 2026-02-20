import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list">
    <div class="caption-overlay"></div>
  </div>
  <input id="grid-width-slider" type="range" min="50" max="360" value="160">
  <button id="caption-toggle"></button>
`;

let applyCaptionVisibility;
let setCaptionsVisibility;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  applyCaptionVisibility = mod.applyCaptionVisibility;
  setCaptionsVisibility = mod.setCaptionsVisibility;
});

describe("caption toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.getElementById("caption-toggle").className = "";
    document.documentElement.classList.remove("hide-captions");
    setCaptionsVisibility(true);
  });

  test("button disabled when tiles small", () => {
    applyCaptionVisibility(100);
    const btn = document.getElementById("caption-toggle");
    expect(btn.classList.contains("disabled")).toBe(true);
    expect(btn.title).toMatch(/increase tile size/i);
  });

  test("click toggles visibility", () => {
    const btn = document.getElementById("caption-toggle");
    applyCaptionVisibility(200);
    setCaptionsVisibility(false);
    expect(document.documentElement.classList.contains("hide-captions")).toBe(
      true,
    );
    expect(btn.classList.contains("active")).toBe(false);
    setCaptionsVisibility(true);
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
