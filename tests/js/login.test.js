import { jest } from "@jest/globals";

document.body.innerHTML = `
  <form id="login-form">
    <input id="username" name="username" />
    <input id="password" name="password" />
    <div id="login-error" class="hidden"></div>
    <input id="remember" type="checkbox" name="remember" />
  </form>
`;

let initLogin;
let attemptAutoLogin;

beforeAll(async () => {
  const mod = await import("../../app/static/js/login.js");
  initLogin = mod.initLogin;
  attemptAutoLogin = mod.attemptAutoLogin;
});

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
  window.IS_LOGGED_IN = false;
});

test("shows error when fields empty", () => {
  initLogin();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const form = document.getElementById("login-form");
  const evt = new Event("submit", { bubbles: true, cancelable: true });
  form.dispatchEvent(evt);
  const err = document.getElementById("login-error");
  expect(evt.defaultPrevented).toBe(true);
  expect(err.classList.contains("hidden")).toBe(false);
  expect(err.textContent).toBe("Username and password are required.");
});

test("never stores credentials when remember checked", () => {
  initLogin();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const form = document.getElementById("login-form");
  form.elements.username.value = "alice";
  form.elements.password.value = "secret";
  form.elements.remember.checked = true;
  const evt = new Event("submit", { bubbles: true, cancelable: true });
  form.dispatchEvent(evt);
  const stored = localStorage.getItem("autoLogin");
  expect(stored).toBeNull();
  expect(evt.defaultPrevented).toBe(false);
});

test("clears stored credentials when checkbox unchecked", () => {
  localStorage.setItem(
    "autoLogin",
    JSON.stringify({ username: "alice", password: "secret" }),
  );
  initLogin();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const form = document.getElementById("login-form");
  form.elements.username.value = "alice";
  form.elements.password.value = "secret";
  form.elements.remember.checked = false;
  const evt = new Event("submit", { bubbles: true, cancelable: true });
  form.dispatchEvent(evt);
  expect(localStorage.getItem("autoLogin")).toBeNull();
});

test("purges legacy credentials without sending them", async () => {
  localStorage.setItem("autoLogin", JSON.stringify({ username: "bob", password: "pw" }));
  global.fetch = jest.fn();
  expect(await attemptAutoLogin()).toBe(false);
  expect(fetch).not.toHaveBeenCalled();
  expect(localStorage.getItem("autoLogin")).toBeNull();
});

test("failed auto login clears stored credentials", async () => {
  localStorage.setItem(
    "autoLogin",
    JSON.stringify({ username: "carol", password: "pw" }),
  );
  global.fetch = jest.fn(() =>
    Promise.resolve({
      redirected: false,
      url: "/login",
      ok: false,
      status: 401,
    }),
  );
  const result = await attemptAutoLogin();
  expect(result).toBe(false);
  expect(localStorage.getItem("autoLogin")).toBeNull();
});
