"""Provide colorized logging and URL sanitization helpers.

The module defines a colored :class:`logging.Formatter` and a simple
rate limiting filter to prevent log spam.  ``sanitize_url`` strips
credentials from strings before logging them to avoid leaking secrets in
diagnostic output.
"""

import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ColorFormatter(logging.Formatter):
    """Add ANSI colors to log level names for console output."""

    COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[96m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Return formatted record with level name colorized.

        Args:
            record: Log record to format.

        Returns:
            Formatted log message including ANSI color codes.
        """

        original_levelname = record.levelname
        level_color = self.COLORS.get(record.levelno, "")
        if level_color:
            record.levelname = f"{level_color}{record.levelname}{self.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class RateLimitFilter(logging.Filter):
    """Filter that suppresses duplicate log messages for a period of time."""

    def __init__(self, interval: float = 60.0):
        """Initialize rate limiting filter.

        Args:
            interval: Seconds to suppress duplicate messages.
        """

        super().__init__()
        self.interval = interval
        self.last_emit: dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        """Return ``True`` if ``record`` should be emitted.

        Args:
            record: Log record being considered.

        Returns:
            ``True`` when message is not rate-limited.
        """

        message = record.getMessage()
        now = time.monotonic()
        last_time = self.last_emit.get(message, 0.0)
        if now - last_time < self.interval:
            return False
        self.last_emit[message] = now
        return True


def sanitize_url(url: str) -> str:
    """Return *url* stripped of any embedded credentials."""

    if not url:
        return url
    try:
        parts = urlparse(url)
        if parts.username or parts.password:
            netloc = parts.hostname or ""
            if parts.port:
                netloc += f":{parts.port}"
            parts = parts._replace(netloc=netloc)
            return parts.geturl()
    except Exception as exc:
        logger.debug("Failed to sanitize URL %s: %s", url, exc)
    return url
