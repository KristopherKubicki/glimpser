"""An assertion failure must never leave later routes without authentication."""

import unittest

from app import routes
from tests.test_notification_settings import NotificationTestMixin


def test_nested_notification_clients_restore_auth_even_after_failure():
    original = (routes.login_required, routes.session, routes.SessionLocal)

    class FailingCase(unittest.TestCase, NotificationTestMixin):
        def runTest(self):
            self.create_client(motion=False)
            self.create_client(motion=True)
            self.fail("simulate a request assertion failing")

    result = unittest.TestResult()
    FailingCase().run(result)
    assert len(result.failures) == 1
    assert not result.errors
    assert routes.login_required is original[0]
    assert routes.session is original[1]
    assert routes.SessionLocal is original[2]
