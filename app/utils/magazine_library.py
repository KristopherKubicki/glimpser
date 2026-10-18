"""Read only fully published, locally generated video magazine editions."""

import json
import re
from pathlib import Path

ROOT = Path.home() / ".local/share/glimpser-magazine/editions"
EDITION = re.compile(r"(?:weekly|monthly|quarterly|yearly|pilot)-[0-9-]{8,10}\Z")
ASSETS = {"film.mp4", "report.html", "manifest.json", "observations.json"}


def editions(root: Path = ROOT) -> list[dict]:
    """List only editions with both a publication manifest and completed film."""
    result = []
    for folder in root.glob("*"):
        if not EDITION.fullmatch(folder.name) or folder.is_symlink():
            continue
        try:
            data = json.loads((folder / "manifest.json").read_text())
            if data.get("id") != folder.name or not (folder / "film.mp4").is_file():
                continue
            result.append(
                {
                    "id": folder.name,
                    "minutes": round(float(data["duration"]) / 60, 1),
                    "chapters": len(data["chapters"]),
                    "published_at": data["published_at"],
                }
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(result, key=lambda row: row["published_at"], reverse=True)
