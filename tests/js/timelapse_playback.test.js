import { jest } from "@jest/globals";
import { mountTimelapse } from "../../app/static/js/timelapse_preview.js";

test.each(["history", "503", "network"])(
  "%s: history playback survives optional replay failure and cleans up",
  async (mode) => {
    jest.useFakeTimers();
    const oldFetch = global.fetch;
    const oldCreate = URL.createObjectURL;
    const oldRevoke = URL.revokeObjectURL;
    const hidden = jest.spyOn(document, "hidden", "get").mockReturnValue(false);
    URL.createObjectURL = jest.fn(() => "blob:history");
    URL.revokeObjectURL = jest.fn();
    const end = Date.now() / 1000;
    const historyResponse = () => ({
      ok: true,
      headers: new Map([
        ["X-Timelapse-Start", String(end - 3600)],
        ["X-Timelapse-End", String(end)],
        ["X-Timelapse-Frames", "24"],
        ["X-Timelapse-Duration", "20"],
      ]),
      blob: async () => new Blob(["clip"]),
    });
    global.fetch = jest.fn(async (url) => {
      if (url.startsWith("/event_buffer/")) {
        if (mode === "network") throw new TypeError("offline replay");
        return { ok: false, status: 503 };
      }
      return historyResponse();
    });
    const scene = document.createElement("section");
    scene.dataset.heroReplayAvailable = String(mode !== "history");
    scene.innerHTML = '<div class="landing-hero-media"></div>';
    document.body.append(scene);
    const ready = jest.fn();
    const originalCreate = document.createElement.bind(document);
    let image;
    const create = jest
      .spyOn(document, "createElement")
      .mockImplementation((tag) => {
        const node = originalCreate(tag);
        if (tag === "img") image = node;
        return node;
      });
    let clip;
    try {
      clip = mountTimelapse(`TestHistory-${mode}`, scene, { onReady: ready });
      for (let i = 0; i < 8; i++) await Promise.resolve();
      expect(global.fetch).toHaveBeenCalledTimes(mode === "history" ? 1 : 2);
      image.onload();
      expect(scene.textContent).toContain("RECORDED HISTORY");
      expect(scene.textContent).toContain("20s left · Next: latest capture");
      jest.advanceTimersByTime(10000);
      expect(scene.querySelector("progress").value).toBe(0.5);
      expect(scene.textContent).toContain("10s left");
      jest.advanceTimersByTime(10000);
      expect(scene.querySelector(".kiosk-timelapse")).toBeNull();
      expect(scene.classList.contains("has-timelapse")).toBe(false);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:history");
      expect(ready).toHaveBeenCalledWith(20);
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      clip?.dispose();
      create.mockRestore();
      hidden.mockRestore();
      scene.remove();
      global.fetch = oldFetch;
      URL.createObjectURL = oldCreate;
      URL.revokeObjectURL = oldRevoke;
      jest.useRealTimers();
    }
  },
);

test.each(["dispose", "deadline"])(
  "%s prevents late replay failure from starting history",
  async (reason) => {
    jest.useFakeTimers();
    const originalFetch = global.fetch;
    let rejectReplay;
    global.fetch = jest.fn(
      () =>
        new Promise((resolve, reject) => {
          rejectReplay = reject;
        }),
    );
    const scene = document.createElement("section");
    scene.dataset.heroReplayAvailable = "true";
    scene.innerHTML =
      '<div class="landing-hero-media"><img alt="Current capture"></div>';
    const clip = mountTimelapse(`Late-${reason}`, scene);
    try {
      if (reason === "dispose") clip.dispose();
      else jest.advanceTimersByTime(8000);
      rejectReplay(new Error("late failure"));
      for (let i = 0; i < 8; i++) await Promise.resolve();
      expect(global.fetch).toHaveBeenCalledTimes(1);
      expect(scene.querySelector("img").alt).toBe("Current capture");
      expect(scene.querySelector(".kiosk-timelapse")).toBeNull();
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      clip.dispose();
      global.fetch = originalFetch;
      jest.useRealTimers();
    }
  },
);
