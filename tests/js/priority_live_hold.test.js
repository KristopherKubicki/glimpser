import { jest } from "@jest/globals";
import { createPriorityAlert } from "../../app/static/js/priority_alert.js";
test("live readiness resets both alert countdown and automatic return deadline", () => {
  jest.useFakeTimers();
  const finish = jest.fn();
  const alert = createPriorityAlert(
    { camera_name: "FrontDoor" },
    30000,
    finish,
  );
  jest.advanceTimersByTime(12000);
  alert.holdLive(45000);
  expect(alert.node.textContent).toContain("Returning in 45s");
  jest.advanceTimersByTime(30000);
  expect(finish).not.toHaveBeenCalled();
  jest.advanceTimersByTime(15000);
  expect(finish).toHaveBeenCalledTimes(1);
  alert.dispose();
  jest.useRealTimers();
});
