import { jest } from "@jest/globals";

document.body.innerHTML = "<div></div>";

global.Notification = jest.fn();
Notification.permission = "granted";
Notification.requestPermission = jest.fn(() => Promise.resolve("granted"));

let initNotifications;
let originalEventSource;
let originalServiceWorker;

beforeAll(async () => {
  const mod = await import("../../app/static/js/notifications.js");
  initNotifications = mod.initNotifications;
  originalEventSource = global.EventSource;
  originalServiceWorker = navigator.serviceWorker;
});

describe("notifications.js", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
    navigator.serviceWorker = originalServiceWorker;
    delete window.VAPID_PUBLIC_KEY;
  });

  test("listens for events and shows notifications", () => {
    const esInstance = { onmessage: null };
    global.EventSource = jest.fn(() => esInstance);

    initNotifications();
    expect(EventSource).toHaveBeenCalledWith("/stream_notifications");

    esInstance.onmessage({
      data: JSON.stringify({ title: "Hi", body: "There" }),
    });
    expect(Notification).toHaveBeenCalledWith("Hi", { body: "There" });
  });

  test("subscribes to push notifications", async () => {
    const esInstance = { onmessage: null };
    global.EventSource = jest.fn(() => esInstance);
    const subscribe = jest.fn(() =>
      Promise.resolve({ endpoint: "e", keys: { p256dh: "k", auth: "a" } }),
    );
    const reg = {
      pushManager: {
        getSubscription: jest.fn(() => Promise.resolve(null)),
        subscribe,
      },
    };
    navigator.serviceWorker = { ready: Promise.resolve(reg) };
    global.fetch = jest.fn(() => Promise.resolve());
    window.VAPID_PUBLIC_KEY = "pub";

    await initNotifications();
    await Promise.resolve();
    await Promise.resolve();

    expect(subscribe).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(
      "/register_push",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
