import { jest } from "@jest/globals";
import { prepareRotationImage } from "../../app/static/js/landing.js";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test("keeps the stage until a usable image loads", () => {
  const image = document.createElement("img");
  Object.defineProperties(image, {
    complete: { value: true },
    naturalWidth: { value: 640 },
    naturalHeight: { value: 480 },
  });
  const ready = jest.fn();
  const failed = jest.fn();
  prepareRotationImage(image, ready, failed);
  expect(ready).not.toHaveBeenCalled();
  jest.runAllTimers();
  expect(ready).toHaveBeenCalledTimes(1);
  expect(failed).not.toHaveBeenCalled();
});

test("times out an incomplete image once", () => {
  const image = document.createElement("img");
  Object.defineProperty(image, "complete", { value: false });
  const ready = jest.fn();
  const failed = jest.fn();
  prepareRotationImage(image, ready, failed);
  jest.advanceTimersByTime(8000);
  image.dispatchEvent(new Event("error"));
  expect(failed).toHaveBeenCalledTimes(1);
  expect(ready).not.toHaveBeenCalled();
});

test("disposal cancels pending work and callbacks", () => {
  const image = document.createElement("img");
  const ready = jest.fn();
  const failed = jest.fn();
  prepareRotationImage(image, ready, failed).dispose();
  image.dispatchEvent(new Event("load"));
  image.dispatchEvent(new Event("error"));
  jest.runAllTimers();
  expect(ready).not.toHaveBeenCalled();
  expect(failed).not.toHaveBeenCalled();
});
