import { jest } from "@jest/globals";

let initNetworkBanner;

beforeAll(async () => {
  const mod = await import("../../app/static/js/network_banner.js");
  initNetworkBanner = mod.initNetworkBanner;
});

beforeEach(() => {
  document.body.innerHTML =
    '<div id="network-banner" class="network-banner"></div>';
  global.fetch = jest.fn();
  window.IS_LOGGED_IN = true;
  jest.clearAllMocks();
});

test("does nothing when not logged in", () => {
  window.IS_LOGGED_IN = false;
  initNetworkBanner();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(fetch).not.toHaveBeenCalled();
  const banner = document.getElementById("network-banner");
  expect(banner.classList.contains("show")).toBe(false);
});

test("shows banner when offline", async () => {
  global.fetch.mockResolvedValueOnce({
    json: () => Promise.resolve({ online: false }),
  });
  initNetworkBanner();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await Promise.resolve();
  const banner = document.getElementById("network-banner");
  expect(fetch).toHaveBeenCalledWith("/network_status");
  expect(banner.classList.contains("show")).toBe(true);
  expect(banner.textContent).toBe("Offline mode");
});
