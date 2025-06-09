import { jest } from "@jest/globals";

let initSubnetInput;

beforeAll(async () => {
  const mod = await import("../../app/static/js/discovery.js");
  initSubnetInput = mod.initSubnetInput;
});

beforeEach(() => {
  document.body.innerHTML =
    '<input id="cidr-input"><datalist id="cidr-options"></datalist>';
  global.fetch = jest.fn(() =>
    Promise.resolve({ json: () => Promise.resolve(["192.168.0.0/24"]) }),
  );
  HTMLInputElement.prototype.setCustomValidity = jest.fn();
});

test("populates subnet options", async () => {
  initSubnetInput();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await Promise.resolve();
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledWith("/discover/subnets");
  const options = document.querySelectorAll("#cidr-options option");
  expect(options).toHaveLength(1);
  expect(options[0].value).toBe("192.168.0.0/24");
});

test("validates CIDR input", async () => {
  initSubnetInput();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await Promise.resolve();
  await Promise.resolve();
  const input = document.getElementById("cidr-input");
  input.value = "bad";
  input.dispatchEvent(new Event("input"));
  expect(HTMLInputElement.prototype.setCustomValidity).toHaveBeenCalledWith(
    "Invalid CIDR",
  );
  input.value = "192.168.1.0/24";
  input.dispatchEvent(new Event("input"));
  expect(HTMLInputElement.prototype.setCustomValidity).toHaveBeenLastCalledWith(
    "",
  );
});
