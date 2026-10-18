"""High-severity npm gate with one operator-approved, expiring dev exception."""

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ADVISORY = "GHSA-vfj7-8cjw-p6xm"
EXPIRES = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
SEVERITIES = {"info", "low", "moderate", "high", "critical"}


def validate_exception(lock, now):
    """Reject expired policy or any production installation of braces."""
    if now >= EXPIRES:
        raise ValueError("braces exception expired; review and remove it")
    packages = lock["packages"]
    nodes = [p for p in packages if p.endswith("node_modules/braces")]
    if not nodes or any(packages[p].get("dev") is not True for p in nodes):
        raise ValueError("braces exception requires exclusively dev dependencies")


def evaluate(report, lock, now):
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
            if (
                cause.get("url") == f"https://github.com/advisories/{ADVISORY}"
                and cause.get("name") == "braces"
                and name == "braces"
            ):
                validate_exception(lock, now)
                if not vuln["nodes"] or any(
                    lock["packages"].get(p, {}).get("dev") is not True
                    for p in vuln["nodes"]
                ):
                    raise ValueError("advisory contains a non-dev or missing package")
                print(
                    f"Approved dev-only exception: {ADVISORY}; expires {EXPIRES.isoformat()}"
                )
            else:
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
    parser.add_argument("--owasp-suppression", type=Path)
    args = parser.parse_args()
    try:
        lock = json.loads(Path("package-lock.json").read_text())
        now = dt.datetime.now(dt.timezone.utc)
        if args.owasp_suppression:
            validate_exception(lock, now)
            args.owasp_suppression.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<suppressions xmlns="https://jeremylong.github.io/DependencyCheck/dependency-suppression.1.3.xsd">\n'
                '  <suppress until="2026-10-25Z">\n'
                "    <notes>Operator approved dev-only braces exception, 2026-10-18.</notes>\n"
                '    <packageUrl regex="true">^pkg:npm/braces@3\\.0\\.3$</packageUrl>\n'
                f"    <vulnerabilityName>{ADVISORY}</vulnerabilityName>\n"
                "  </suppress>\n</suppressions>\n"
            )
            return 0
        result = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise ValueError(f"npm audit failed with exit {result.returncode}")
        failures = evaluate(json.loads(result.stdout), lock, now)
        for failure in failures:
            print(f"Blocking npm advisory: {failure}", file=sys.stderr)
        return int(bool(failures))
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"npm audit gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
