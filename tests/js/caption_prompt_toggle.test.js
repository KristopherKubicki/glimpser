import { jest } from "@jest/globals";

let initCaptions;

beforeAll(async () => {
  const mod = await import("../../app/static/js/captions.js");
  initCaptions = mod.initCaptions;
});

beforeEach(() => {
  document.body.innerHTML = `
    <button class="tab-link" data-tab="one"></button>
    <div id="one" class="tab-content"></div>
    <input type="radio" name="caption-field" value="caption" checked>
    <input type="radio" name="caption-field" value="prompt">
    <table id="camera-table">
      <thead>
        <tr><th class="view-header">Caption</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>cam1</td>
          <td>
            <div class="chat-prompt"><textarea>hello</textarea></div>
            <div class="chat-response"><div class="last-caption">world</div></div>
          </td>
        </tr>
      </tbody>
    </table>`;
  localStorage.clear();
});

test("toggle switches view", () => {
  initCaptions();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.querySelector("input[value='prompt']").click();
  expect(document.querySelector(".view-header").textContent).toBe("Prompt");
  expect(
    document.querySelector(".chat-response").classList.contains("hidden"),
  ).toBe(true);
  expect(
    document.querySelector(".chat-prompt").classList.contains("hidden"),
  ).toBe(false);
});
