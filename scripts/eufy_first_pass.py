#!/usr/bin/env python3
"""Prime Eufy cloud auth once and capture one frame per imported camera.

This script is useful right after solving Eufy captcha. It avoids waiting for
the scheduler and takes a first screenshot pass for imported ``eufy://`` templates.
"""

from __future__ import annotations

import argparse
import base64
import json
from typing import Any

from app.utils import eufy_cloud, template_manager
from app.utils.eufy_first_pass import capture_profile_first_pass


def _decode_and_save_captcha(profile: str) -> str | None:
    challenge = eufy_cloud.get_native_captcha(profile)
    if not challenge:
        return None
    data_url = str(challenge.get("captcha_item") or "").strip()
    if not data_url.startswith("data:image"):
        return None
    try:
        encoded = data_url.split(",", 1)[1]
        payload = base64.b64decode(encoded)
    except Exception:
        return None

    path = f"/tmp/eufy_captcha_{profile}.png"
    try:
        with open(path, "wb") as fh:
            fh.write(payload)
        return path
    except OSError:
        return None


def _select_profiles(args: argparse.Namespace) -> list[str]:
    if args.profile:
        return [str(args.profile).strip().lower()]

    profiles: set[str] = set()
    for tmpl in template_manager.get_templates().values():
        url = str(tmpl.get("url") or "")
        if not url.startswith("eufy://"):
            continue
        profile, _did = eufy_cloud.parse_eufy_url(url)
        if profile:
            profiles.add(profile)
    if not profiles:
        return ["default"]
    return sorted(profiles)


def _ensure_eufy_auth_ready(
    profile: str, *, timeout: float, captcha_code: str | None, interactive: bool
) -> None:
    try:
        eufy_cloud.list_devices(profile, timeout=timeout)
        return
    except eufy_cloud.EufyCaptchaRequired:
        pass

    code = (captcha_code or "").strip()
    if not code and interactive:
        path = _decode_and_save_captcha(profile)
        if path:
            print(f"[{profile}] Captcha image saved to: {path}")
        else:
            print(
                f"[{profile}] Captcha required; image available in Eufy integration UI."
            )
        code = input(f"[{profile}] Enter captcha code: ").strip()

    if not code:
        raise RuntimeError(
            f"[{profile}] Captcha required. Re-run with --captcha-code or --interactive."
        )

    eufy_cloud.submit_native_captcha(profile, code, timeout=timeout)
    # Verify session can list devices before starting capture loop.
    eufy_cloud.list_devices(profile, timeout=timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Take first-pass snapshots for imported Eufy templates."
    )
    parser.add_argument(
        "--profile",
        default="",
        help="Eufy profile to process (default: auto-detect from imported templates).",
    )
    parser.add_argument(
        "--captcha-code",
        default="",
        help="Captcha code to submit once if Eufy requires verification.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for captcha when required.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-request timeout in seconds (default: 20).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON results.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profiles = _select_profiles(args)
    all_results: list[dict[str, Any]] = []

    for profile in profiles:
        try:
            _ensure_eufy_auth_ready(
                profile,
                timeout=float(args.timeout),
                captcha_code=(args.captcha_code or "").strip() or None,
                interactive=bool(args.interactive),
            )
        except Exception as exc:
            print(f"Profile {profile}: {exc}")
            return 2
        all_results.extend(
            capture_profile_first_pass(profile, timeout=float(args.timeout))
        )

    ok = sum(1 for row in all_results if row.get("ok"))
    failed = sum(1 for row in all_results if not row.get("ok"))
    summary = {"ok": ok, "failed": failed, "total": len(all_results)}

    if args.json:
        print(json.dumps({"summary": summary, "results": all_results}, indent=2))
    else:
        print(
            f"Eufy first pass complete: {ok} ok, {failed} failed, {len(all_results)} total"
        )
        for row in all_results:
            if row.get("ok"):
                print(f"OK   {row['name']} -> {row['file']}")
            else:
                print(f"FAIL {row['name']} -> {row['error']}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
