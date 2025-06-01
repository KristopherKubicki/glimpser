import os
from threading import Thread
from werkzeug.serving import make_server

import pytest

from app import create_app

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import WebDriverException
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
    app = create_app(enable_watchdog=False, schedule=False)
    data_dir = tmp_path_factory.mktemp("data")
    prev_cwd = os.getcwd()
    os.chdir(data_dir)
    server = ServerThread(app)
    server.start()
    yield f"http://127.0.0.1:{server.port}"
    server.shutdown()
    os.chdir(prev_cwd)


def _create_driver():
    if webdriver is None:
        return None
    for constructor, options in [
        (webdriver.Chrome, webdriver.ChromeOptions()),
        (webdriver.Firefox, webdriver.FirefoxOptions()),
    ]:
        try:
            if "Chrome" in constructor.__name__:
                options.add_argument("--headless=new")
            else:
                options.add_argument("--headless")
            return constructor(options=options)
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
