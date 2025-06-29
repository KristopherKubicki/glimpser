import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

from app.utils.db import commit_with_retry


class TestCommitWithRetry(unittest.TestCase):
    def test_retries_on_locked_error(self):
        session = MagicMock()
        session.commit.side_effect = [
            OperationalError("stmt", {}, Exception("database is locked")),
            None,
        ]
        with patch("app.utils.db.time.sleep") as mock_sleep:
            commit_with_retry(session, attempts=2, delay=0)
        self.assertEqual(session.commit.call_count, 2)
        session.rollback.assert_called_once()
        mock_sleep.assert_called_once()

    def test_raises_non_locked_error(self):
        session = MagicMock()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("other"))
        with self.assertRaises(OperationalError):
            commit_with_retry(session, attempts=2, delay=0)
        session.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
