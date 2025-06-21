import os
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.utils.screenshots import capture_screenshot_and_har

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.firefox.service import Service as FirefoxService
except Exception:  # pragma: no cover - optional dependency may not be present
    webdriver = None  # type: ignore
    ChromeService = None  # type: ignore
    FirefoxService = None  # type: ignore
    WebDriverException = Exception


def _create_driver():
    if webdriver is None:
        return None

    drivers = [
        (webdriver.Chrome, webdriver.ChromeOptions(), shutil.which("chromedriver")),
        (webdriver.Firefox, webdriver.FirefoxOptions(), shutil.which("geckodriver")),
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
        except Exception:
            continue
    return None


@pytest.fixture(scope="module")
def browser():
    driver = _create_driver()
    if driver is None:
        pytest.skip("Web driver not available")
    yield driver
    try:
        driver.quit()
    except Exception:
        pass


@pytest.fixture()
def http_server(tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<html><body>Hello</body></html>")
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
    yield url
    server.shutdown()
    thread.join()


def test_capture_pipeline(browser, http_server, tmp_path, monkeypatch):
    output = tmp_path / "out.png"
    monkeypatch.setattr("app.utils.screenshots.is_system_online", lambda: True)
    monkeypatch.setattr(
        "app.utils.screenshots.launch_headless_chrome", lambda *a, **k: browser
    )
    monkeypatch.setattr("app.utils.screenshots.get_chrome_version", lambda p: 120)
    monkeypatch.setattr(
        "app.utils.screenshots.get_chrome_path", lambda: "/usr/bin/chrome"
    )
    monkeypatch.setattr(
        "app.utils.screenshots._finalize_screenshot", lambda *a, **k: True
    )
    assert capture_screenshot_and_har(http_server, str(output))
    assert output.exists()
