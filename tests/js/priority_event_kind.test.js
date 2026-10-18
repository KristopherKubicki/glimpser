import { jest } from "@jest/globals";
import { createPriorityAlert } from "../../app/static/js/priority_alert.js";

test.each([
  ["doorbell", "DOORBELL RANG"],
  ["person", "PERSON DETECTED"],
  ["motion", "MOTION DETECTED"],
])("labels %s activity accurately", (kind, label) => {
  jest.useFakeTimers();
  const alert = createPriorityAlert(
    { kind, camera_name: "Beach_Google_Front_Door" },
    30000,
    jest.fn(),
  );
  expect(alert.node.querySelector(".kiosk-priority-label").textContent).toBe(label);
  expect(alert.node.getAttribute("aria-label")).toContain(label.toLowerCase());
  alert.dispose();
  jest.useRealTimers();
});
