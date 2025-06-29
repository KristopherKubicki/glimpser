"""Tests for e2e web."""
import argparse
import importlib
import os
import shutil
from threading import Thread
from unittest.mock import patch

import pytest
import pytest_socket
from werkzeug.serving import make_server

if os.environ.get("NO_NETWORK") == "1" or os.environ.get("SKIP_E2E") == "1":
    pytest.skip("E2E tests disabled due to no network", allow_module_level=True)

pytest_socket.enable_socket()

import app

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.service import Service as FirefoxService
except Exception:  # pragma: no cover - optional dependency may not be present
    webdriver = None  # type: ignore
    By = None
    WebDriverException = Exception


class ServerThread(Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", 0, app)
        self.port = self.server.server_port

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    application = app.create_app(enable_watchdog=False, schedule=False, log_cache=False)
    data_dir = tmp_path_factory.mktemp("data")
    prev_cwd = os.getcwd()
    os.chdir(data_dir)
    server = ServerThread(application)
    server.start()
    yield f"http://127.0.0.1:{server.port}"
    server.shutdown()
    os.chdir(prev_cwd)


def _create_driver():
    if webdriver is None:
        return None

    # Skip attempts to download drivers from the internet by only trying
    # browsers with executables already present on the system. Selenium's
    # automatic driver download can take a long time and hang in CI where
    # network access is restricted.
    drivers = [
        (
            webdriver.Chrome,
            webdriver.ChromeOptions(),
            shutil.which("chromedriver"),
        ),
        (
            webdriver.Firefox,
            webdriver.FirefoxOptions(),
            shutil.which("geckodriver"),
        ),
    ]
    for constructor, options, driver_path in drivers:
        if not driver_path:
            continue
        try:
            if "Chrome" in constructor.__name__:
                options.add_argument("--headless=new")
                service = ChromeService(executable_path=driver_path)
            else:
                options.add_argument("--headless")
                service = FirefoxService(executable_path=driver_path)
            return constructor(service=service, options=options)
        except WebDriverException:
            continue
        except Exception:  # pragma: no cover - fallback
            continue
    return None


@pytest.fixture(scope="module")
def browser():
    driver = _create_driver()
    if driver is None:
        pytest.skip("Web driver not available")
    yield driver
    driver.quit()


@pytest.fixture(scope="module")
def live_server_with_user(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("creds")
    db_path = os.path.join(data_dir, "test.db")
    env = {"GLIMPSER_DATABASE_PATH": db_path}
    patcher = patch.dict(os.environ, env)
    patcher.start()

    secure_patch = patch("app.config.SESSION_COOKIE_SECURE", False)
    secure_patch.start()

    import app.config as config
    import app.routes as routes
    import app.utils.db as db
    import generate_credentials

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(routes)
    importlib.reload(app)

    args = argparse.Namespace(
        db_path=db_path,
        username="e2e",
        password="secret",  # pragma: allowlist secret
        update_password=False,
        secret_key="secretkey",  # pragma: allowlist secret
        update_key=False,
    )
    generate_credentials.generate_credentials(args)

    application = app.create_app(enable_watchdog=False, schedule=False, log_cache=False)
    prev_cwd = os.getcwd()
    os.chdir(data_dir)
    server = ServerThread(application)
    server.start()
    yield f"http://127.0.0.1:{server.port}"
    server.shutdown()
    os.chdir(prev_cwd)

    secure_patch.stop()
    patcher.stop()
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(routes)
    importlib.reload(app)


def test_root_redirects_to_login(live_server, browser):
    browser.get(live_server)
    assert "/login" in browser.current_url


def test_login_page_has_form(live_server, browser):
    browser.get(f"{live_server}/login")
    assert "Glimpser" in browser.title
    username = browser.find_element(By.NAME, "username")
    password = browser.find_element(By.NAME, "password")
    assert username is not None
    assert password is not None


def test_login_and_redirect(live_server_with_user, browser):
    browser.get(f"{live_server_with_user}/login")
    browser.find_element(By.NAME, "username").send_keys("e2e")
    browser.find_element(By.NAME, "password").send_keys("secret")
    browser.find_element(By.CSS_SELECTOR, "form input[type=submit]").click()
    assert browser.current_url.endswith("/")
    browser.find_element(By.ID, "search-input")
    browser.get(f"{live_server_with_user}/live")
    video = browser.find_element(By.ID, "live-video")
    slider = browser.find_element(By.ID, "speed-slider")
    assert video is not None
    assert slider is not None
