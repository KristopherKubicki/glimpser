import { jest } from "@jest/globals";
import { fetchJson } from "../../app/static/js/fetch_utils.js";

describe("fetchJson", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("returns parsed json when response ok", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      }),
    );
    const data = await fetchJson("/api/test");
    expect(data).toEqual({ ok: true });
  });

  test("throws text error when response not ok", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        text: () => Promise.resolve("Bad"),
        statusText: "Bad",
      }),
    );
    await expect(fetchJson("/api/fail")).rejects.toThrow("Bad");
  });

  test("rethrows fetch rejection and logs", async () => {
    const err = new Error("Network");
    global.fetch = jest.fn(() => Promise.reject(err));
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    await expect(fetchJson("/api/error")).rejects.toThrow(err);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
