import unittest
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.utils.db import commit_with_retry


class TestCommitWithRetry(unittest.TestCase):
    def test_locked_error_is_not_hidden_by_empty_commit(self):
        session = MagicMock()
        error = OperationalError("stmt", {}, Exception("database is locked"))
        session.commit.side_effect = [error, None]
        with self.assertRaises(OperationalError) as caught:
            commit_with_retry(session, attempts=2, delay=0)
        self.assertIs(caught.exception, error)
        session.commit.assert_called_once()
        session.rollback.assert_not_called()

    def test_raises_non_locked_error(self):
        session = MagicMock()
        session.commit.side_effect = OperationalError("stmt", {}, Exception("other"))
        with self.assertRaises(OperationalError):
            commit_with_retry(session, attempts=2, delay=0)
        session.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
