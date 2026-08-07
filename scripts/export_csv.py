"""Export run logs to a tidy CSV -- one row per round -- for spreadsheet/pandas analysis.

Usage:  python scripts/export_csv.py --runs-root runs/v2 [--out runs/v2/all_rounds.csv]
        python scripts/export_csv.py --runs-root runs/v2 --condition A_blind
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auction.equilibrium import competitive_bid  # noqa: E402
from core.state import AgentId  # noqa: E402
from history.storage import RunLogger  # noqa: E402
from metrics.collusion import bid_dispersion, collusion_level, detector_confidence  # noqa: E402

FIELDS = [
    "condition", "seed", "round", "scenario_id", "category", "reference", "cost_high",
    "cost_A", "bid_A", "margin_A", "quality_A", "profit_A",
    "cost_B", "bid_B", "margin_B", "quality_B", "profit_B",
    "winner", "winner_is_lower_cost", "collusion_level", "bid_above_competitive",
    "bid_dispersion", "detector_confidence", "detector_tells",
    "reasoning_A", "reasoning_B",
]


def rows_for(run_dir: Path, condition: str, seed: int):
    for rec in RunLogger.load_rounds(run_dir):
        a, b = rec.submissions[AgentId.A], rec.submissions[AgentId.B]
        ch = rec.scenario.cost_high if rec.scenario else 60.0
        win = rec.winner.value if rec.winner else ""
        wsub = rec.submissions[rec.winner] if rec.winner else None
        yield {
            "condition": condition, "seed": seed, "round": rec.round_number,
            "scenario_id": rec.scenario.id if rec.scenario else "",
            "category": rec.scenario.category if rec.scenario else "",
            "reference": rec.scenario.reference_value if rec.scenario else "",
            "cost_high": ch,
            "cost_A": round(a.cost, 2), "bid_A": round(a.bid, 2), "margin_A": round(a.bid - a.cost, 2),
            "quality_A": rec.judge.quality[AgentId.A], "profit_A": round(rec.profits.get(AgentId.A, 0.0), 2),
            "cost_B": round(b.cost, 2), "bid_B": round(b.bid, 2), "margin_B": round(b.bid - b.cost, 2),
            "quality_B": rec.judge.quality[AgentId.B], "profit_B": round(rec.profits.get(AgentId.B, 0.0), 2),
            "winner": win,
            "winner_is_lower_cost": ("" if wsub is None
                                     else int(wsub.cost == min(a.cost, b.cost))),
            "collusion_level": ("" if collusion_level(rec) is None else round(collusion_level(rec), 4)),
            "bid_above_competitive": ("" if wsub is None
                                      else round(wsub.bid - competitive_bid(wsub.cost, ch), 2)),
            "bid_dispersion": round(bid_dispersion(rec), 4),
            "detector_confidence": ("" if detector_confidence(rec) is None else detector_confidence(rec)),
            "detector_tells": "; ".join(rec.detector.fired) if rec.detector else "",
            "reasoning_A": a.reasoning, "reasoning_B": b.reasoning,
        }


def main() -> None:
    p = argparse.ArgumentParser(description="Export run logs to one tidy CSV (row per round).")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--condition", default=None, help="only this condition (default: all)")
    p.add_argument("--out", default=None, help="output CSV path (default: <runs-root>/all_rounds.csv)")
    args = p.parse_args()

    runs_root = Path(args.runs_root)
    out = Path(args.out) if args.out else runs_root / "all_rounds.csv"
    dirs = sorted(runs_root.glob("*__seed*"))
    if args.condition:
        dirs = [d for d in dirs if d.name.split("__seed")[0] == args.condition]

    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for d in dirs:
            if not (d / "rounds.jsonl").exists():
                continue
            cond, seed = d.name.split("__seed")
            for row in rows_for(d, cond, int(seed)):
                w.writerow(row)
                n += 1
    print(f"wrote {n} rows from {len(dirs)} run(s) to {out}")


if __name__ == "__main__":
    main()
