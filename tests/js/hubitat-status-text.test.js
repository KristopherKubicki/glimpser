import { readFileSync } from "node:fs";

const source = readFileSync("app/utils/screenshots.py", "utf8");
const start = source.indexOf("    function statusLinesForItem(item) {");
const end = source.indexOf("    function tileVisualStyle(item) {", start);
const extract = new Function(
  "item",
  source.slice(start, end) + "\nreturn statusLinesForItem(item);",
);

function lines(html) {
  document.body.innerHTML = `<div id="fixture">${html}</div>`;
  return extract(document.getElementById("fixture"));
}

test.each(["on", "off"])("preserves reported switch state %s", (state) => {
  expect(lines(`<span>Sump pump</span><button>${state}</button>`)).toEqual([
    "Sump pump",
    state,
  ]);
});
test("preserves role-button state and omits menu/action text", () => {
  expect(
    lines(
      '<span>Pump</span><div role="button">on</div><button>Refresh</button><i class="material-icons">settings</i>',
    ),
  ).toEqual(["Pump", "on"]);
});
test("preserves sensor readings", () => {
  expect(
    lines("<span>Water</span><span>dry</span><button>Configure</button>"),
  ).toEqual(["Water", "dry"]);
});
test("does not invent a missing state", () => {
  expect(lines("<span>Missing</span><button>Refresh</button>")).toEqual([
    "Missing",
  ]);
});

test("reads legacy switch state when icon text is hidden", () => {
  document.body.innerHTML =
    '<div class="tile switch"><div class="tile-title">Attic Fan</div><div class="tile-primary off"><i class="material-icons"></i></div></div>';
  expect(extract(document.body.firstElementChild)).toEqual([
    "Attic Fan",
    "off",
  ]);
});
test("preserves an explicit legacy unknown state", () => {
  document.body.innerHTML =
    '<div class="tile presence"><div class="tile-title">Dryer Running</div><div class="tile-primary unknown"></div></div>';
  expect(extract(document.body.firstElementChild)).toEqual([
    "Dryer Running",
    "Unknown",
  ]);
});
test("does not guess from missing or conflicting legacy state classes", () => {
  for (const classes of ["", "on off"]) {
    document.body.innerHTML = `<div class="tile switch"><div class="tile-title">Fan</div><div class="tile-primary ${classes}"></div></div>`;
    expect(extract(document.body.firstElementChild)).toEqual(["Fan"]);
  }
});

test.each([
  "open",
  "closed",
  "opening",
  "closing",
  "locked",
  "unlocked",
  "unknown",
])("preserves explicit Hubitat reported state %s", (state) => {
  expect(
    lines(
      `<span>Gate</span><button aria-label="Open garage door"><span class="dashboard-text-color">${state}</span></button>`,
    ),
  ).toEqual(["Gate", state]);
});
test("does not mistake an action label for reported door state", () => {
  expect(
    lines(
      '<span>Gate</span><button aria-label="Open garage door">Open</button>',
    ),
  ).toEqual(["Gate"]);
});
