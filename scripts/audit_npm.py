"""Fail-closed npm high/critical advisory gate."""

import argparse
import json
import subprocess
import sys

SEVERITIES = {"info", "low", "moderate", "high", "critical"}


def evaluate(report):
    """Check advisory roots, retaining npm's high/critical failure threshold."""
    if report.get("auditReportVersion") != 2 or "error" in report:
        raise ValueError("invalid npm audit response")
    vulnerabilities = report["vulnerabilities"]
    if not isinstance(vulnerabilities, dict):
        raise ValueError("invalid vulnerability map")
    failures = []
    for name, vuln in vulnerabilities.items():
        if vuln["severity"] not in SEVERITIES or not vuln["via"]:
            raise ValueError("invalid vulnerability severity or advisory chain")
        for cause in vuln["via"]:
            if isinstance(cause, str):
                if cause not in vulnerabilities:
                    raise ValueError("missing transitive advisory")
                continue  # Every referenced entry is independently checked.
            if cause["severity"] not in SEVERITIES:
                raise ValueError("unknown advisory severity")
            if cause["severity"] not in {"high", "critical"}:
                continue
            failures.append(cause.get("url", name))
    # Reject cyclic/empty high-severity graphs without a concrete advisory root.
    for name, vuln in vulnerabilities.items():
        if vuln["severity"] not in {"high", "critical"}:
            continue
        pending, seen, roots = [name], set(), []
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            for cause in vulnerabilities[current]["via"]:
                if isinstance(cause, str):
                    pending.append(cause)
                else:
                    roots.append(cause)
        if not any(c["severity"] in {"high", "critical"} for c in roots):
            raise ValueError("high-severity finding lacks a concrete advisory")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise ValueError(f"npm audit failed with exit {result.returncode}")
        failures = evaluate(json.loads(result.stdout))
        for failure in failures:
            print(f"Blocking npm advisory: {failure}", file=sys.stderr)
        return int(bool(failures))
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"npm audit gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
