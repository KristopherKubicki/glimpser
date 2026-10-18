"""Apply conservative horizon-leveling defaults to known horizon cameras."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/glimpser.db")
DEFAULT_ROI = "0.04,0.12,0.92,0.36"
CANDIDATES: dict[str, tuple[str, str]] = {
    "AtwaterBuoyMilwaukee": ("roll", "0.04,0.00,0.92,0.30"),
    "BeachNorthJetty": ("smooth", "0.12,0.00,0.76,0.18"),
    "BeachShore": ("smooth", "0.08,0.00,0.84,0.18"),
    "CarthageCollegeKenosha": ("smooth", "0.04,0.00,0.92,0.30"),
    "DempsterBoatLaunch": ("roll", "0.04,0.00,0.92,0.30"),
    "DuluthCanalCam": ("roll", "0.04,0.08,0.92,0.42"),
    "Edgewater": ("smooth", "0.04,0.00,0.92,0.30"),
    "GrandMaraisHarborCam": ("roll", "0.04,0.08,0.92,0.42"),
    "GreenBayBuoyUWM": ("roll", "0.04,0.00,0.92,0.30"),
    "Kenosha": ("smooth", "0.04,0.00,0.92,0.30"),
    "LincolnPark2800LakeShore": ("smooth", "0.04,0.00,0.92,0.30"),
    "MackinacBridgeNorth": ("smooth", "0.04,0.08,0.92,0.42"),
    "MackinacBridgeSouth": ("smooth", "0.08,0.00,0.84,0.18"),
    "MuskegonSouthPierhead": ("smooth", "0.04,0.00,0.92,0.30"),
    "NorthPointMarina": ("roll", "0.08,0.00,0.84,0.18"),
    "Northwestern": ("smooth", "0.04,0.00,0.92,0.30"),
    "PortHuronBoatnerd": ("roll", "0.08,0.00,0.84,0.18"),
    "PortHuronStreamTime": ("roll", "0.04,0.08,0.92,0.42"),
    "SheboyganBeach": ("roll", "0.08,0.00,0.84,0.18"),
    "SheboyganMarina": ("roll", "0.04,0.08,0.92,0.42"),
    "SkylineSooLocks": ("roll", "0.08,0.00,0.84,0.18"),
    "SooLocksLive": ("roll", "0.04,0.08,0.92,0.42"),
    "SouthHavenNorthPierGLERL": ("smooth", "0.08,0.00,0.84,0.18"),
    "SouthHavenPierDeckGLERL": ("smooth", "0.04,0.00,0.92,0.30"),
    "SouthHavenPierLightGLERL": ("smooth", "0.04,0.08,0.92,0.42"),
    "SouthHavenSouthBeachGLERL": ("smooth", "0.08,0.00,0.84,0.18"),
    "SouthportMarinaKenosha": ("smooth", DEFAULT_ROI),
    "WaukeganBuoy": ("roll", DEFAULT_ROI),
    "WaukeganHarbor": ("roll", "0.04,0.00,0.92,0.30"),
    "WaukeganHarborWeatherbug": ("smooth", DEFAULT_ROI),
    "WinthropBuoy": ("roll", DEFAULT_ROI),
}


def apply_horizon_level_candidates(
    db_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """Update matching templates and return ``(updated, skipped, missing)`` names."""

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "select name, coalesce(horizon_level_mode, '') from templates"
        ).fetchall()
        existing_modes = {str(name): str(mode or "") for name, mode in rows}
        updated: list[str] = []
        skipped: list[str] = []
        missing: list[str] = []

        for name, (mode, roi) in CANDIDATES.items():
            current = existing_modes.get(name)
            if current is None:
                missing.append(name)
                continue
            if current.strip() and not force:
                skipped.append(name)
                continue
            updated.append(name)
            if dry_run:
                continue
            conn.execute(
                """
                update templates
                   set horizon_level_mode = ?,
                       horizon_level_roi = ?
                 where name = ?
                """,
                (mode, roi, name),
            )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return updated, skipped, missing
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing horizon_level_mode values",
    )
    args = parser.parse_args()

    updated, skipped, missing = apply_horizon_level_candidates(
        args.db,
        dry_run=args.dry_run,
        force=args.force,
    )
    action = "would update" if args.dry_run else "updated"
    print(f"{action}: {', '.join(updated) if updated else '-'}")
    print(f"skipped: {', '.join(skipped) if skipped else '-'}")
    print(f"missing: {', '.join(missing) if missing else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
