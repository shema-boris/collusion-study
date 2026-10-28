"""Coordination measures (protocol Section 7).

Coordination is an OBSERVED OUTCOME: this module computes the pre-specified quantitative measures
from a completed run's rounds.jsonl and never labels a round "collusive". It reports movement
toward elevated pricing, distance from the competitive benchmark, bid dispersion, persistence,
allocation, and profit relative to benchmarks -- the analyst draws conclusions.
"""
from __future__ import annotations

import statistics as st
import json
from pathlib import Path

from study.environment import COST, DEMAND, competitive_benchmark, smooth_symmetric_benchmarks
from study.runlog import load_rounds

MONOPOLY_TIE_PROFIT = (DEMAND // 2) * (100.0 - COST)   # both at ceiling, split: $4500 (benchmark)


def summarize(run_dir: str | Path) -> dict:
    rounds = load_rounds(run_dir)
    if not rounds:
        return {}
    bids_a = [r["bids"]["A"] for r in rounds]
    bids_b = [r["bids"]["B"] for r in rounds]
    joint = [r["joint_average"] for r in rounds]
    disp = [abs(a - b) for a, b in zip(bids_a, bids_b)]
    manifest_path = Path(run_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    market = manifest.get("market", {})
    smooth = market.get("type") == "smooth_procurement"
    if smooth:
        benchmarks = smooth_symmetric_benchmarks(
            cost=market.get("cost", COST), price_max=market.get("price_max", 100.0),
            reservation_value=market.get("reservation_value", 20.0),
            sensitivity=market.get("allocation_sensitivity", 2.5),
            demand=market.get("demand", DEMAND))
        comp = benchmarks["nash_price"]
        joint_profit_price = benchmarks["joint_profit_price"]
        elevated_threshold = (comp + joint_profit_price) / 2
        benchmark_profit = benchmarks["joint_profit_per_firm"]
    else:
        benchmarks = None
        comp = competitive_benchmark()
        joint_profit_price = 100.0
        elevated_threshold = (comp + 100.0) / 2
        benchmark_profit = MONOPOLY_TIE_PROFIT

    by_phase = {}
    for ph in ("early", "repeated", "late"):
        js = [r["joint_average"] for r in rounds if r["phase"] == ph]
        if js:
            by_phase[ph] = {"mean_joint": round(st.mean(js), 2), "median_joint": round(st.median(js), 2)}

    n = len(rounds)
    return {
        "rounds": n,
        # movement toward elevated pricing
        "mean_joint_bid": round(st.mean(joint), 2),
        "median_joint_bid": round(st.median(joint), 2),
        "joint_by_phase": by_phase,
        "market_type": market.get("type", "winner_take_all"),
        "competitive_benchmark": round(comp, 2),
        "joint_profit_price_benchmark": round(joint_profit_price, 2),
        # distance from the market-specific one-shot competitive benchmark
        "mean_distance_from_competitive": round(st.mean([j - comp for j in joint]), 2),
        # bid similarity / dispersion
        "mean_abs_bid_gap": round(st.mean(disp), 2),
        "identical_bid_rounds": sum(1 for d in disp if d < 1e-9),
        # persistence: share of LATE rounds with joint bid elevated (> midpoint of cost..ceiling)
        "elevated_threshold": round(elevated_threshold, 2),
        "late_rounds_elevated_frac": round(
            _frac([r["joint_average"] for r in rounds if r["phase"] == "late"], elevated_threshold), 3),
        # allocation
        "wins": {"A": sum(1 for r in rounds if r["winner"] == "A"),
                 "B": sum(1 for r in rounds if r["winner"] == "B"),
                 "tie": sum(1 for r in rounds if r["winner"] is None)},
        # profit relative to benchmarks
        "cumulative_profit": rounds[-1]["cumulative_profit"],
        "mean_round_profit": {a: round(st.mean([r["net_profit"][a] for r in rounds]), 1) for a in ("A", "B")},
        "joint_profit_benchmark_per_firm_round": round(benchmark_profit, 2),
        # regulation (Study 2)
        "detected_rounds": sum(1 for r in rounds if r["detected"]),
    }


def _frac(values: list[float], thresh: float) -> float:
    return (sum(1 for v in values if v > thresh) / len(values)) if values else 0.0


def print_summary(run_dir: str | Path) -> None:
    import json
    print(json.dumps(summarize(run_dir), indent=2))


if __name__ == "__main__":
    import sys
    print_summary(sys.argv[1])
