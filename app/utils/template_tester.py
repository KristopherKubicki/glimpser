from typing import Any, Dict

from .screenshots import (
    get_content_type,
    is_image_url,
    is_pdf_url,
    is_video_stream_url,
    should_use_lightweight_browser,
    should_use_phantom_browser,
    is_enhanced,
)


def test_template_settings(
    url: str,
    *,
    popup_xpath: str = "",
    dedicated_xpath: str = "",
    browser: bool = False,
    headless: bool = False,
    stealth: bool = False,
    danger: bool = False,
) -> Dict[str, Any]:
    """Return capture suggestions for ``url``."""

    content_type, _ = get_content_type(url, danger, stealth=stealth)

    if is_image_url(url, content_type):
        collector = "image"
    elif is_pdf_url(url, content_type):
        collector = "pdf"
    elif is_video_stream_url(url, content_type):
        collector = "stream"
    elif is_enhanced(url):
        collector = "ytdlp"
    elif should_use_lightweight_browser(
        url, dedicated_xpath, popup_xpath, headless, stealth, browser, danger
    ):
        collector = "lightweight"
    elif should_use_phantom_browser(
        url, dedicated_xpath, popup_xpath, headless, stealth, browser, danger
    ):
        collector = "phantom"
    else:
        collector = "browser"

    checkboxes = {"browser": False, "headless": False, "stealth": False}
    if collector not in {"image", "pdf", "stream"}:
        checkboxes["headless"] = True
        if collector in {"browser", "phantom"}:
            checkboxes["browser"] = True
        if collector == "browser":
            checkboxes["stealth"] = True

    return {
        "content_type": content_type,
        "collector": collector,
        "checkboxes": checkboxes,
    }
