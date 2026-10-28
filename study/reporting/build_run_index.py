"""Build a reproducible CSV inventory from run manifests; never edits raw runs."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def build(root: Path, output: Path) -> Path:
    rows = []
    for path in sorted(root.rglob("manifest.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        reg = m.get("regulation") or {}
        rows.append({
            "run_dir": str(path.parent), "study": m.get("study"),
            "status": m.get("status"), "analysis_eligible": m.get("analysis_eligible"),
            "market": (m.get("market") or {}).get("type"), "seed": m.get("seed"),
            "model_a": (m.get("models") or {}).get("A"),
            "model_b": (m.get("models") or {}).get("B"),
            "detector_model": reg.get("detector_model"),
            "penalty_fraction": reg.get("penalty_fraction"),
            "horizon": m.get("horizon"), "completed_rounds": m.get("generated_rounds", 0),
            "failure_reason": m.get("failure_reason", ""),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["run_dir"]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("runs_study"))
    p.add_argument("--output", type=Path, default=Path("paper/generated/run_index.csv"))
    a = p.parse_args()
    print(build(a.root, a.output))
