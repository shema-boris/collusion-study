"""Raw per-round logging (DESIGN.md §10). Metrics are computed offline from these.

Each round is written as its own JSON file so a run can be inspected, resumed, or
re-analysed without re-spending tokens.
"""
from __future__ import annotations

from pathlib import Path

from core.state import RoundRecord


def save_round(run_dir: str | Path, rec: RoundRecord) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"round_{rec.round_number:03d}.json"
    path.write_text(rec.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_run(run_dir: str | Path) -> list[RoundRecord]:
    run_dir = Path(run_dir)
    files = sorted(run_dir.glob("round_*.json"))
    return [RoundRecord.model_validate_json(f.read_text(encoding="utf-8")) for f in files]
