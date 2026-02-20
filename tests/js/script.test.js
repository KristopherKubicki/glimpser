import { jest } from "@jest/globals";

// Mock the fetch function
global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () =>
      Promise.resolve({
        /* mock data */
      }),
  }),
);

// Mock the DOM elements
document.body.innerHTML = `
  <div id="template-list"></div>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

global.slider = document.getElementById("grid-width-slider");

let loadTemplates;
let updateGridLayout;
let timeAgo;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  loadTemplates = mod.loadTemplates;
  updateGridLayout = mod.updateGridLayout;
  timeAgo = mod.timeAgo;
});

describe("script.js", () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
  });

  test("loadTemplates fetches data and updates the DOM", async () => {
    // Mock the fetch response
    global.fetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/json" },
      json: () =>
        Promise.resolve({
          template1: { last_screenshot_time: new Date().toISOString() },
          template2: { last_screenshot_time: new Date().toISOString() },
        }),
    });

    await loadTemplates();

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/templates\?group=all&search=$/),
      expect.objectContaining({
        cache: "no-cache",
        headers: { Accept: "application/json" },
      }),
    );
    expect(document.getElementById("template-list").children.length).toBe(2);
  });

  test("updateGridLayout changes layout based on screen size", () => {
    const templateList = document.getElementById("template-list");

    // Mock mobile device
    window.matchMedia = jest.fn().mockImplementation((query) => ({
      matches: query === "(hover: none) and (max-width: 767px)",
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    updateGridLayout();
    expect(templateList.style.gridTemplateColumns).toBe("1fr");

    // Mock desktop device
    window.matchMedia = jest.fn().mockImplementation((query) => ({
      matches: query !== "(hover: none) and (max-width: 767px)",
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    updateGridLayout();
    expect(templateList.style.gridTemplateColumns).toBe(
      "repeat(auto-fit, minmax(50px, var(--tile-size)))",
    );
  });

  test("timeAgo returns correct human-readable time", () => {
    const now = new Date();
    const oneMinuteAgo = new Date(now.getTime() - 60000);
    const oneHourAgo = new Date(now.getTime() - 3600000);
    const oneDayAgo = new Date(now.getTime() - 86400000);

    expect(timeAgo(now)).toBe("just now");
    expect(timeAgo(oneMinuteAgo)).toBe("1m ago");
    expect(timeAgo(oneHourAgo)).toBe("1h ago");
    expect(timeAgo(oneDayAgo)).toBe("1d ago");
  });

  test("timeAgo handles null and undefined", () => {
    expect(timeAgo(null)).toBe("just now");
    expect(timeAgo(undefined)).toBe("just now");
  });

  test("timeAgo treats naive timestamps as UTC", () => {
    process.env.TZ = "America/Chicago";
    jest.useFakeTimers().setSystemTime(new Date("2024-01-01T01:00:00Z"));
    expect(timeAgo("2024-01-01 00:00:00")).toBe("1h ago");
    jest.useRealTimers();
    delete process.env.TZ;
  });

  test("timeAgo prefers local interpretation when UTC looks stale", () => {
    process.env.TZ = "America/Chicago";
    jest.useFakeTimers().setSystemTime(new Date("2024-01-01T16:00:00Z"));
    expect(timeAgo("2024-01-01 10:00:00")).toBe("just now");
    jest.useRealTimers();
    delete process.env.TZ;
  });
});
