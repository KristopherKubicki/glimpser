import { liveCameraLabel } from "../../app/static/js/kiosk_live.js";

afterEach(() => document.body.replaceChildren());

test("uses installation labels only from private settings", () => {
  const settings = document.createElement("script");
  settings.id = "kiosk-live-settings";
  settings.type = "application/json";
  settings.textContent = JSON.stringify({
    ExampleCamera: { provider: "stream", label: "Configured entrance" },
  });
  document.body.append(settings);
  expect(liveCameraLabel("ExampleCamera")).toBe("Configured entrance");
  expect(liveCameraLabel("Other_Camera")).toBe("Other Camera");
});

test("malformed settings retain a generic camera name", () => {
  const settings = document.createElement("script");
  settings.id = "kiosk-live-settings";
  settings.type = "application/json";
  settings.textContent = "{";
  document.body.append(settings);
  expect(liveCameraLabel("Example_Camera")).toBe("Example Camera");
});
