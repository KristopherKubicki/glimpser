import { jest } from "@jest/globals";

document.body.innerHTML = `
<div id="hotkeys-modal" style="display:none"></div>
`;

let initHotkeys;

beforeAll(async () => {
  const mod = await import("../../app/static/js/hotkeys.js");
  initHotkeys = mod.initHotkeys;
});

test("? shows overlay and Esc hides it", () => {
  initHotkeys();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const modal = document.getElementById("hotkeys-modal");
  const showEvt = new KeyboardEvent("keydown", { key: "?" });
  document.dispatchEvent(showEvt);
  expect(modal.style.display).toBe("block");
  const hideEvt = new KeyboardEvent("keydown", { key: "Escape" });
  document.dispatchEvent(hideEvt);
  expect(modal.style.display).toBe("none");
});
