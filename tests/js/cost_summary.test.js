import { jest } from "@jest/globals";

document.body.innerHTML = `
  <input id="start-date" type="date">
  <input id="end-date" type="date">
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
  test("since restart fills start date", async () => {
    initCostSummary(0);
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const btn = document.getElementById("since-restart");
    btn.click();
    await Promise.resolve();
    const start = document.getElementById("start-date");
    expect(start.value).toBe("1970-01-01");
  });
});
