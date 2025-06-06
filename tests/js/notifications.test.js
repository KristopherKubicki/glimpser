import { jest } from "@jest/globals";

document.body.innerHTML = "<div></div>";

global.Notification = jest.fn();
Notification.permission = "granted";
Notification.requestPermission = jest.fn(() => Promise.resolve("granted"));

let initNotifications;

beforeAll(async () => {
  const mod = await import("../../app/static/js/notifications.js");
  initNotifications = mod.initNotifications;
});

describe("notifications.js", () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
});
