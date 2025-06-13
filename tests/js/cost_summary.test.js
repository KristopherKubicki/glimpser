import { jest } from "@jest/globals";

document.body.innerHTML = `
  <select id="cost-group"></select>
  <input id="cost-range" type="range" value="7">
  <button id="since-restart"></button>
  <button id="load-cost"></button>
  <table id="cost-table"><tbody></tbody></table>
  <canvas id="costChart"></canvas>
`;

let initCostSummary;

beforeAll(async () => {
  ({ initCostSummary } = await import("../../app/static/js/costs.js"));
});

global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ cam1: { cost: "$1.00", tokens: 1 } }),
  }),
);

global.Chart = jest.fn(function () {
  this.update = jest.fn();
});

describe("cost summary", () => {
  test("since restart adjusts slider", async () => {
    initCostSummary(0);
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const btn = document.getElementById("since-restart");
    btn.click();
    await Promise.resolve();
    const range = document.getElementById("cost-range");
    expect(parseInt(range.value, 10)).toBeGreaterThan(0);
  });
});
