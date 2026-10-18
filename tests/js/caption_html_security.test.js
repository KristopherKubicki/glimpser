import { jest } from "@jest/globals";
import { initCaptions } from "../../app/static/js/captions.js";

test("chat questions and model answers remain text", async () => {
  document.body.innerHTML = '<button class="tab-link"></button><input id="chat-question"><button id="chat-submit"></button><div id="chat-answer"></div><table id="captions-table"><tbody></tbody></table>';
  const malicious = '<img src=x onerror="alert(1)">';
  global.fetch = jest.fn(() => Promise.resolve({ json: () => Promise.resolve({ answer: malicious }) }));
  initCaptions();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("chat-question").value = malicious;
  document.getElementById("chat-submit").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const table = document.querySelector("#captions-table tbody");
  expect(table.textContent).toContain(`Q: ${malicious}`);
  expect(table.textContent).toContain(`A: ${malicious}`);
  expect(table.querySelector("img")).toBeNull();
});
