import { jest } from "@jest/globals";

document.body.innerHTML = `
  <input id="cost-range" type="range" value="7">
  <span id="cost-range-label"></span>
  <table id="cost-table"><tbody></tbody></table>
  <canvas id="costChart"></canvas>
  <script id="cost-data" type="application/json">[]</script>
`;

let initCosts;
let groupSmallValues;

beforeAll(async () => {
  ({ initCosts, groupSmallValues } = await import(
    "../../app/static/js/costs.js"
  ));
});

global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ cam1: { cost: "$1.00", tokens: 1 } }),
  }),
);

global.Chart = jest.fn(function () {
  this.update = jest.fn();
});

test("slider triggers fetch", async () => {
  initCosts();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledTimes(1);
  const slider = document.getElementById("cost-range");
  fetch.mockClear();
  slider.value = "10";
  slider.dispatchEvent(new Event("change"));
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("groups bottom rows", () => {
  const rows = Array.from({ length: 20 }, (_, i) => ({
    name: `cam${i}`,
    tokens: 1,
    cost: i,
  }));
  const grouped = groupSmallValues(rows, 15);
  expect(grouped.length).toBe(6); // 5 top + Other
  const other = grouped[grouped.length - 1];
  expect(other.name).toBe("Other");
  expect(other.cost).toBeGreaterThan(0);
});
