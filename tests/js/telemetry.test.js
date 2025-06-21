import { jest } from "@jest/globals";

let sendTelemetry;

beforeAll(async () => {
  ({ sendTelemetry } = await import("../../app/static/js/telemetry.js"));
});

test("sendTelemetry posts event data", () => {
  const catchMock = jest.fn();
  global.fetch = jest.fn(() => ({ catch: catchMock }));
  sendTelemetry("event", { foo: "bar" });
  expect(fetch).toHaveBeenCalledWith(
    "/telemetry",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ event: "event", data: { foo: "bar" } }),
    }),
  );
  expect(catchMock).toHaveBeenCalledWith(expect.any(Function));
});
