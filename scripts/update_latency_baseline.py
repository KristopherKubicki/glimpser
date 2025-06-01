"""Write aggregated latency metrics to docs/latency_baseline.json."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.profiling import get_latency_stats

BASELINE_PATH = "docs/latency_baseline.json"


def main() -> None:
    stats = get_latency_stats()
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
