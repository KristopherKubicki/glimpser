import { presentationValue } from "../../app/static/js/presentation_config.js";

afterEach(() => { document.body.innerHTML = ""; });
test("generic defaults without installation settings", () => {
  expect(presentationValue("Home arrivals")).toBe("Home arrivals");
});
test("reads configured labels as data", () => {
  const settings = document.createElement("script");
  settings.id = "presentation-settings";
  settings.type = "application/json";
  settings.textContent = JSON.stringify({"Home arrivals": "Example property arrivals"});
  document.body.append(settings);
  expect(presentationValue("Home arrivals")).toBe("Example property arrivals");
});
test.each(["null", "[]", "broken", '{"Home arrivals":42}', '{"Home arrivals":""}'])("invalid settings retain defaults: %s", (value) => {
  document.body.innerHTML = '<script id="presentation-settings" type="application/json"></script>';
  document.getElementById("presentation-settings").textContent = value;
  expect(presentationValue("Home arrivals")).toBe("Home arrivals");
});
