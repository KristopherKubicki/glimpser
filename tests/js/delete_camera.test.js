import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="delete-camera-modal" class="modal">
    <p id="delete-camera-modal-message"></p>
    <button id="delete-camera-confirm"></button>
    <button id="delete-camera-cancel"></button>
    <span id="delete-camera-close"></span>
  </div>
  <div class="templateDiv" data-name="cam1"></div>
`;

global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ status: "success" }),
  }),
);

let confirmDeleteCamera;

beforeAll(async () => {
  ({ confirmDeleteCamera } = await import("../../app/static/js/templates.js"));
});

test("confirmDeleteCamera shows modal and sends request", () => {
  confirmDeleteCamera("cam1");
  expect(document.getElementById("delete-camera-modal").style.display).toBe(
    "block",
  );
  document.getElementById("delete-camera-confirm").click();
  expect(fetch).toHaveBeenCalledWith(
    "/templates",
    expect.objectContaining({ method: "DELETE" }),
  );
});
