import logging
import os
import time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from pyvirtualdisplay import Display

from app.utils.browser_config import add_options
from app.utils.network_utils import network_idle_condition, is_port_open
from app.utils.image_processing import remove_background, add_timestamp
from app.config import UA


def capture_screenshot_and_har(
    url,
    output_path,
    popup_xpath=None,
    dedicated_selector=None,
    timeout=30,
    name="unknown",
    invert=False,
    proxy=None,
    stealth=False,
    dark=True,
    headless=True,
    danger=False,
):
    """
    Capture a screenshot of a URL using headless Chrome, optionally removing a popup before taking the screenshot.

    :param url: URL to capture.
    :param output_path: Name of the screenshot.
    :param popup_xpath: Optional XPath for a popup element to remove.
    """
    lsuccess = False
    ltime = time.time()

    if danger and not is_port_open("127.0.0.1", 9222):
        logging.warn("Danger port is not open - won't properly connect")
        return False

    display = None
    driver = None
    chrome_service = None
    main_version = None
    current_window_handle = None
    new_window_handle = None
    try:
        if danger:
            options = webdriver.ChromeOptions()
            options.page_load_strategy = "none"
            options.binary_location = "/usr/bin/google-chrome"
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--new-window")

            user_data_dir = os.path.expanduser("~/.config/google-chrome")
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--profile-directory=Default")
            options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            options.set_capability(
                "goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"}
            )
            driver = webdriver.Chrome(options=options)
        else:
            chrome_service = Service(ChromeDriverManager().install())
            driver_path = chrome_service.path
            main_version = extract_version(driver_path)

            if stealth:
                options = webdriver.ChromeOptions()
                options.set_capability(
                    "goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"}
                )

                if headless:
                    driver = uc.Chrome(
                        version_main=main_version,
                        service=chrome_service,
                        use_subprocess=False,
                        headless=True,
                        options=options,
                    )
                else:
                    display = Display(visible=0, size=(1920, 1080))
                    display.start()
                    driver = uc.Chrome(
                        version_main=main_version,
                        service=chrome_service,
                        use_subprocess=False,
                        options=options,
                    )
            else:
                chrome_options = add_options(webdriver.ChromeOptions())
                if headless:
                    chrome_options.add_argument("--headless")
                else:
                    display = Display(visible=0, size=(1920, 1080))
                    display.start()
                chrome_options.add_argument(f"--user-agent={UA}")
                driver = webdriver.Chrome(
                    service=chrome_service, options=chrome_options
                )

        if danger:
            current_window_handle = driver.current_window_handle
            try:
                script = """(function(){let l=Date.now();['mousemove','keydown','scroll','click'].forEach(e=>document.addEventListener(e,()=>l=Date.now()));window.getIdleTime=()=>Date.now()-l;})();"""
                lret1 = driver.execute_script(script)
                time.sleep(10)
                lret = driver.execute_script("return window.getIdleTime();")
                print("LRET", lret1, lret)
                if lret < 10000:
                    print(" activity...")
                    logging.warn("activity detected")
                    return False
            except Exception as e:
                print("> dupe timeout warning", e)

            current_window_handle = driver.current_window_handle
            driver.execute_script("window.open('', '_blank');")
            driver.switch_to.window(driver.window_handles[-1])
            new_window_handle = driver.current_window_handle
            if new_window_handle is None or new_window_handle == current_window_handle:
                driver.switch_to.window(current_window_handle)
                logging.warn("duplicate session")
                return False

        if not danger:
            driver.set_window_size(1920, 1080)
            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1920,
                    "height": 1080,
                    "mobile": False,
                    "deviceScaleFactor": 1,
                },
            )
            driver.execute_script(
                "window.screen.width = 1920; window.screen.height = 1080;"
            )
            driver.execute_script(
                "window.innerWidth = 1920; window.innerHeight = 1080;"
            )

        if not invert and dark:
            driver.execute_cdp_cmd(
                "Emulation.setAutoDarkModeOverride", {"enabled": True}
            )

        if not danger:
            driver.delete_all_cookies()

        driver.set_page_load_timeout(timeout)
        gtime = time.time()
        driver.get(url)

        if danger and current_window_handle:
            driver.switch_to.window(current_window_handle)

        lret, lstatus = network_idle_condition(driver, url, timeout, stealth)
        if not lret:
            if not stealth:
                max(timeout - (time.time() - ltime), 15)
                logging.warn(
                    f"Vanilla non-idle connection detected {url} at {output_path}, failing over to undetectable chromedriver"
                )
                return False

            if int(lstatus) >= 400:
                return False

        if danger and time.time() - gtime < 10:
            time.sleep(10 - (time.time() - gtime))
        elif time.time() - gtime < 5:
            time.sleep(5 - (time.time() - gtime))

        if popup_xpath:
            try:
                elements = driver.find_elements(By.XPATH, popup_xpath)
                for element in elements:
                    driver.execute_script(
                        """var element = arguments[0]; element.parentNode.removeChild(element); """,
                        element,
                    )
            except Exception:
                pass

        if danger:
            current_window_handle = driver.current_window_handle
            driver.switch_to.window(new_window_handle)

        if dedicated_selector:
            try:
                element = driver.find_element(By.XPATH, dedicated_selector)
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)

                if "//iframe" in dedicated_selector:
                    driver.switch_to.frame(element)
                    try:
                        element = driver.find_element(By.XPATH, "//video")
                        element.screenshot(output_path)
                    except Exception:
                        driver.save_screenshot(output_path)

                if not os.path.exists(output_path):
                    element.screenshot(output_path)
            except Exception:
                chrome_service = Service(ChromeDriverManager().install())

        if not os.path.exists(output_path):
            driver.save_screenshot(output_path)

        if danger:
            driver.close()
            new_window_handle = None
            driver.switch_to.window(current_window_handle)

        if os.path.exists(output_path):
            from PIL import Image

            image = Image.open(output_path)
            image = image.convert("RGB")
            image = remove_background(image)
            image.save(output_path, "PNG")
            if os.path.exists(output_path):
                add_timestamp(output_path, name, invert=invert)

        logging.info(f"Successfully captured screenshot for {url} at {output_path}")
        lsuccess = True
    except TimeoutException:
        logging.warn(f"Timed out waiting for network to be idle for {url}")
    except Exception as e:
        print(f"Error capturing screenshot for {url}", e, main_version)
        logging.error(
            f"Error capturing screenshot for {url}: {e} stealth: %s headless: %s"
            % (stealth, headless)
        )
    finally:
        if danger:
            if new_window_handle:
                try:
                    driver.switch_to.window(new_window_handle)
                    if driver and current_window_handle != new_window_handle:
                        driver.close()
                except Exception as e:
                    print(">>>1", e)
                    pass

            if current_window_handle:
                try:
                    driver.switch_to.window(current_window_handle)
                except Exception as e:
                    print(">>>2", e)
                    pass
        if driver and not danger:
            driver.quit()
        if display:
            display.stop()

    return lsuccess


def extract_version(driver_path):
    try:
        import re

        match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", driver_path)
        if match:
            return int(match.group(1))
        else:
            raise ValueError("Version number not found in the path.")
    except Exception as e:
        print(f"Error extracting version from path: {driver_path}, error: {e}")
        return 127


def capture_screenshot_and_har_light(
    url, output_path, timeout=30, name="unknown", invert=False, proxy=None, dark=True
):
    """
    Capture a screenshot of a URL using wkhtmltoimage (WebKit).

    :param url: URL to capture.
    :param output_path: Name of the screenshot.
    """
    import shutil
    import subprocess
    from PIL import Image
    from app.utils.image_processing import (
        is_mostly_blank,
        remove_background,
        apply_dark_mode,
        add_timestamp,
    )
    from app.config import UA

    if shutil.which("wkhtmltoimage") is None:
        print("wkhtmltoimage is not installed or not in the system path.")
        return False

    output_path = output_path.replace(".png", ".tmp.png")

    lsuccess = False

    ltime = time.time()

    command = [
        "wkhtmltoimage",
        "--width",
        "1920",
        "--height",
        "1080",
        "--javascript-delay",
        str(5000),
        "--quiet",
        "--zoom",
        "1",
        "--quality",
        "100",
        "--enable-javascript",
        "--custom-header",
        "User-Agent",
        UA,
        "--custom-header-propagation",
        url,
        output_path,
    ]

    try:
        result = subprocess.run(
            command, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
        if result.returncode != 0:
            return False
    except Exception as e:
        if "timed out" not in str(e):
            print(" subprocess issue...", e)
        return False

    if os.path.exists(output_path):
        image = Image.open(output_path)
        try:
            image = image.convert("RGB")
        except Exception:
            print(" .. image exception")
            return False

        if is_mostly_blank(image):
            os.unlink(output_path)
            return False

        image = image.convert("RGB")
        image = remove_background(image)

        if dark:
            image = apply_dark_mode(image)
        image.save(output_path, "PNG")

        if os.path.exists(output_path):
            add_timestamp(output_path, name, invert=invert)
            lsuccess = True
            os.rename(output_path, output_path.replace(".tmp.png", ".png"))
        else:
            os.unlink(output_path)
            lsuccess = False

    logging.info(
        f"Successfully captured light screenshot for {url} at {output_path} {round(time.time() - ltime,3)}"
    )

    return lsuccess
