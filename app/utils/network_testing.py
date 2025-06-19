import json
import time
from typing import List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement


def network_idle_condition(
    driver: WebDriver,
    url: str,
    timeout: int = 30,
    idle_time: float = 0.25,
    stealth: bool = False,
) -> Tuple[bool, int]:
    """
    Returns a function that can be used as a condition for WebDriverWait.
    It checks if the network has been idle for a specified amount of time.

    :param driver: The WebDriver instance.
    :param url: The URL being tested.
    :param timeout: Maximum time to wait for the network to become idle.
    :param idle_time: Time in seconds that the network should be idle.
    :param stealth: Whether to use stealth mode.
    """
    gurl = url.split("#")[0]
    lstatus = 800

    end_time = time.time() + timeout
    not_moving = 0
    while time.time() < end_time:
        if not_moving > 5:
            break

        logs = driver.get_log("performance")
        events = [
            log
            for log in logs
            if "Network.response" in log["message"]
            or "Network.request" in log["message"]
        ]
        for gevent in events:
            levent = json.loads(gevent.get("message"))
            lurl = (
                levent.get("message", {})
                .get("params", {})
                .get("response", {})
                .get("url")
            )
            if lurl == gurl:
                lstatus = (
                    levent.get("message", {})
                    .get("params", {})
                    .get("response", {})
                    .get("status")
                )

                # Treat any 4xx or 5xx response as a failure so the caller can
                # bail out early on server errors.
                if lstatus >= 400:
                    return False, lstatus
        if not events:
            not_moving += 1
        else:
            not_moving = 0
        time.sleep(idle_time)

    if stealth:
        return False, lstatus
    return True, lstatus


def check_network_errors(
    driver: WebDriver, url: str, timeout: int = 30
) -> Tuple[bool, List[str]]:
    """
    Check for network errors during page load.

    :param driver: The WebDriver instance.
    :param url: The URL being tested.
    :param timeout: Maximum time to wait for errors.
    :return: A tuple (bool, list) indicating if errors were found and a list of errors.
    """
    end_time = time.time() + timeout
    errors = []

    while time.time() < end_time:
        logs = driver.get_log("browser")
        for log in logs:
            if log["level"] == "SEVERE":
                if (
                    "Failed to load resource" in log["message"]
                    or "NetworkError" in log["message"]
                ):
                    errors.append(log["message"])

        if errors:
            return True, errors

        time.sleep(0.5)

    return False, errors


def wait_for_element(
    driver: WebDriver, selector: str, timeout: int = 10
) -> Optional[WebElement]:
    """
    Wait for an element to be present on the page.

    :param driver: The WebDriver instance.
    :param selector: CSS selector for the element.
    :param timeout: Maximum time to wait for the element.
    :return: The element if found, None otherwise.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            return element
        except:
            time.sleep(0.5)
    return None
