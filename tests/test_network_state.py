import os
from unittest.mock import patch

from app.utils.network import network_state


def test_network_state_defaults_lan_ok_when_not_configured():
    with patch.dict(os.environ, {"LAN_TEST_HOSTS": ""}, clear=False):
        state = network_state(timeout=1)
    assert state["lan_ok"] is True
    assert state["lan_reason"] in {"not_configured", None}
