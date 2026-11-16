"""Release audit fails closed without advisory exceptions."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "audit_npm", Path(__file__).resolve().parents[1] / "scripts/audit_npm.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


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
                            "url": "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
                        }
                    ],
                },
                "parent": {"severity": "high", "via": ["braces"]},
            },
        },
        {"packages": {"node_modules/braces": {"dev": True}}},
    )


def test_former_exception_blocks(inputs):
    assert audit.evaluate(inputs[0]) == [
        "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm"
    ]


def test_other_high_advisory_blocks(inputs):
    other = copy.deepcopy(inputs[0]["vulnerabilities"]["braces"]["via"][0])
    other["url"] = "https://github.com/advisories/GHSA-other"
    inputs[0]["vulnerabilities"]["braces"]["via"].append(other)
    assert audit.evaluate(inputs[0]) == [
        inputs[0]["vulnerabilities"]["braces"]["via"][0]["url"],
        other["url"],
    ]


def test_moderate_threshold_unchanged(inputs):
    inputs[0]["vulnerabilities"]["moderate"] = {
        "severity": "moderate",
        "via": [{"severity": "moderate", "url": "other"}],
    }
    assert len(audit.evaluate(inputs[0])) == 1


def test_unknown_advisory_reference(inputs):
    inputs[0]["vulnerabilities"]["parent"]["via"] = ["missing"]
    with pytest.raises(ValueError, match="missing transitive"):
        audit.evaluate(inputs[0])


def test_cycle_fails_closed(inputs):
    inputs[0]["vulnerabilities"]["parent"]["via"] = ["parent"]
    with pytest.raises(ValueError, match="concrete advisory"):
        audit.evaluate(inputs[0])


def test_network_error_response(inputs):
    inputs[0]["error"] = {"code": "ENETUNREACH"}
    with pytest.raises(ValueError, match="invalid npm"):
        audit.evaluate(inputs[0])


def test_clean_report_passes():
    assert audit.evaluate({"auditReportVersion": 2, "vulnerabilities": {}}) == []
