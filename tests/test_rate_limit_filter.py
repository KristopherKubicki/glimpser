import io
import logging
import time
import unittest

from app.utils.logging_utils import RateLimitFilter


class TestRateLimitFilter(unittest.TestCase):
    def test_filter_suppresses_duplicates(self):
        logger = logging.getLogger("rate_limit_test")
        logger.setLevel(logging.INFO)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        filt = RateLimitFilter(interval=0.1)
        handler.addFilter(filt)
        logger.addHandler(handler)

        try:
            logger.warning("repeat")
            logger.warning("repeat")
            time.sleep(0.11)
            logger.warning("repeat")
        finally:
            logger.removeHandler(handler)

        output = [line for line in stream.getvalue().splitlines() if line]
        self.assertEqual(len(output), 2)


if __name__ == "__main__":
    unittest.main()
