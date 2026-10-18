"""Release audit exception boundaries."""

import copy
import datetime as dt
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "audit_npm", Path(__file__).resolve().parents[1] / "scripts/audit_npm.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)


@pytest.fixture
def inputs():
    return (
        {
            "auditReportVersion": 2,
            "vulnerabilities": {
                "braces": {
                    "severity": "high",
                    "nodes": ["node_modules/braces"],
                    "via": [
                        {
                            "name": "braces",
                            "severity": "high",
                            "url": f"https://github.com/advisories/{audit.ADVISORY}",
                        }
                    ],
                },
                "parent": {"severity": "high", "via": ["braces"]},
            },
        },
        {"packages": {"node_modules/braces": {"dev": True}}},
    )


def test_approved_transitive_dev_exception(inputs):
    assert audit.evaluate(*inputs, NOW) == []


def test_expiry(inputs):
    with pytest.raises(ValueError, match="expired"):
        audit.evaluate(*inputs, audit.EXPIRES)


@pytest.mark.parametrize("dev", [False, None])
def test_runtime_or_unknown_classification(inputs, dev):
    inputs[1]["packages"]["node_modules/braces"]["dev"] = dev
    with pytest.raises(ValueError, match="dev dependencies"):
        audit.evaluate(*inputs, NOW)


def test_other_high_advisory_blocks(inputs):
    other = copy.deepcopy(inputs[0]["vulnerabilities"]["braces"]["via"][0])
    other["url"] = "https://github.com/advisories/GHSA-other"
    inputs[0]["vulnerabilities"]["braces"]["via"].append(other)
    assert audit.evaluate(*inputs, NOW) == [other["url"]]


def test_moderate_threshold_unchanged(inputs):
    inputs[0]["vulnerabilities"]["moderate"] = {
        "severity": "moderate",
        "via": [{"severity": "moderate", "url": "other"}],
    }
    assert audit.evaluate(*inputs, NOW) == []


def test_unknown_advisory_reference(inputs):
    inputs[0]["vulnerabilities"]["parent"]["via"] = ["missing"]
    with pytest.raises(ValueError, match="missing transitive"):
        audit.evaluate(*inputs, NOW)


def test_cycle_fails_closed(inputs):
    inputs[0]["vulnerabilities"]["parent"]["via"] = ["parent"]
    with pytest.raises(ValueError, match="concrete advisory"):
        audit.evaluate(*inputs, NOW)


def test_network_error_response(inputs):
    inputs[0]["error"] = {"code": "ENETUNREACH"}
    with pytest.raises(ValueError, match="invalid npm"):
        audit.evaluate(*inputs, NOW)
