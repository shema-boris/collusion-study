"""Dump rendered scenarios for manual verification before running experiments.

Usage:  python scripts/preview_scenarios.py [limit]     # default 12
Shows exactly what an agent/judge would read.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auction.scenarios import ScenarioRepository  # noqa: E402


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    repo = ScenarioRepository.load(ROOT / "configs" / "scenarios.yaml")
    print(f"{len(repo)} scenarios in bank; showing first {min(limit, len(repo))}\n")
    for i, scenario in enumerate(repo.all()[:limit], start=1):
        print(f"--- round {i} ---")
        print(scenario.render())
        print("=" * 72)


if __name__ == "__main__":
    main()
