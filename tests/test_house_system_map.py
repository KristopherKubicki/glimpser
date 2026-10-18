"""Isolated tests: never probe the network or load production configuration."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask, abort, request
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inventory(monkeypatch):
    module = load("inventory", "app/utils/house_system_map.py")
    nodes = tuple(
        (
            f"node-{i}",
            f"Node {i}",
            "Personal compute" if i < 7 else "Work compute",
            f"node-{i}.example.test",
            443 if i < 6 else None,
            "Test service",
            "",
            "HTTPS",
        )
        for i in range(8)
    )
    monkeypatch.setattr(module, "NODES", nodes)
    return module


def test_isolation_never_probed(inventory, monkeypatch):
    connect = MagicMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(inventory.socket, "create_connection", connect)
    for node in inventory.NODES:
        if node[4] is None:
            assert inventory._probe(node)["status"] == "isolated"
    connect.assert_not_called()


def test_timeout_is_not_labeled_host_down(inventory, monkeypatch):
    monkeypatch.setattr(
        inventory.socket, "create_connection", MagicMock(side_effect=TimeoutError)
    )
    row = inventory._probe(inventory.NODES[0])
    assert row["status"] == "unreachable"
    assert "from Glimpser" in row["label"]


def test_success_cache_expiry_and_defensive_copy(inventory, monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(inventory.socket, "create_connection", connect)
    first = inventory.snapshot()
    assert first["responding"] == 6
    assert first["isolated"] == 2
    assert connect.call_count == 6
    first["nodes"].clear()
    assert len(inventory.snapshot()["nodes"]) == 8
    assert connect.call_count == 6
    inventory._CACHE_AT -= 31
    inventory.snapshot()
    assert connect.call_count == 12
    assert all(call.kwargs["timeout"] == 0.7 for call in connect.call_args_list)


def test_route_requires_auth_before_probing(inventory, monkeypatch):
    def guard(fn):
        def guarded():
            if not request.headers.get("X-Test-Login"):
                abort(401)
            return fn()

        guarded.__name__ = fn.__name__
        return guarded

    app_stub = types.ModuleType("app")
    app_stub.routes = types.SimpleNamespace(login_required=guard)
    monkeypatch.setitem(sys.modules, "app", app_stub)
    monkeypatch.setitem(sys.modules, "app.utils", types.ModuleType("app.utils"))
    monkeypatch.setitem(
        sys.modules,
        "app.utils.network",
        types.SimpleNamespace(
            is_system_online=lambda: True, network_state=lambda: {"lan_ok": True}
        ),
    )
    monkeypatch.setitem(sys.modules, "app.utils.house_system_map", inventory)
    snap = MagicMock(
        return_value={
            "checked_at": "test",
            "nodes": [],
            "responding": 0,
            "unreachable": 0,
            "isolated": 0,
        }
    )
    monkeypatch.setattr(inventory, "snapshot", snap)
    module = load("network_test", "app/blueprints/network.py")
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.jinja_loader = ChoiceLoader(
        [
            DictLoader({"base.html": "{% block content %}{% endblock %}"}),
            app.jinja_loader,
        ]
    )
    app.register_blueprint(module.create_blueprint())
    client = app.test_client()
    assert client.get("/house-systems").status_code == 401
    snap.assert_not_called()
    response = client.get(
        "/house-systems?host=127.0.0.1", headers={"X-Test-Login": "yes"}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    snap.assert_called_once_with()
    assert client.get("/network_status").status_code == 200


def test_template_escapes_and_distinguishes_unknown(inventory, monkeypatch):
    monkeypatch.setattr(inventory.socket, "create_connection", MagicMock())
    data = inventory.snapshot()
    data["nodes"][0]["name"] = "<script>bad</script>"
    data["nodes"][0]["link"] = "https://service.example.test/dashboard"
    env = Environment(
        loader=ChoiceLoader(
            [
                DictLoader({"base.html": "{% block content %}{% endblock %}"}),
                FileSystemLoader(ROOT / "app/templates"),
            ]
        ),
        autoescape=True,
    )
    result = env.get_template("house_systems.html").render(
        system_map=data, groups=inventory.GROUPS
    )
    assert 'href="https://service.example.test/dashboard"' in result
    assert result.count('href="http') == 1
    assert "<script>bad</script>" not in result
    assert "&lt;script&gt;" in result
    assert "Not probed · isolated" in result
    assert "Personal compute" in result and "Work compute" in result
    assert data["checked_at"] in result
    assert "does not prove" in result
