"""Is each agent bidding a ~constant markup over cost, regardless of cost?

"Markup" = bid - cost (what the agent adds on top of its private cost). This prints, per
condition, the markup level and whether it depends on the agent's cost:

  vs-cost slope / corr ~ 0  AND  lowcost-third markup == highcost-third markup
      -> a FIXED markup (add the same ~$X no matter your cost) -- the coordination-like signature.
  slope / corr large, lowcost-third markup >> highcost-third
      -> cost-responsive COMPETITION (Bayes-Nash bids more margin when cost is low).

Usage:  python scripts/check_markup.py [--runs-root runs/v3]
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.state import AgentId  # noqa: E402
from history.storage import RunLogger  # noqa: E402

ORDER = ["R0", "C1", "S_informed", "A_informed"]


def slope_corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    ss = st.pstdev(xs) * st.pstdev(ys)
    return (sxy / sxx if sxx else 0), (sxy / (len(xs) * ss) if ss else 0)


def main() -> None:
    p = argparse.ArgumentParser(description="Check whether agents bid a ~constant markup over cost.")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "v3"))
    p.add_argument("--seeds", default="0,1,2", help="comma-separated seeds to pool")
    args = p.parse_args()
    runs_root = Path(args.runs_root)
    seeds = [int(s) for s in args.seeds.split(",")]

    print(f"{'condition':12s} {'markup mean+/-sd':>17s} {'vs-cost slope':>14s} {'corr':>7s}"
          f"   lowcost/highcost third")
    for cond in ORDER:
        cost, mk = [], []
        for s in seeds:
            d = runs_root / f"{cond}__seed{s}"
            if not (d / "rounds.jsonl").exists():
                continue
            for r in RunLogger.load_rounds(d):
                for a in (AgentId.A, AgentId.B):
                    sub = r.submissions[a]
                    cost.append(sub.cost)
                    mk.append(sub.bid - sub.cost)
        if not mk:
            print(f"{cond:12s}  (no runs found under {runs_root})")
            continue
        pairs = sorted(zip(cost, mk))
        t = len(pairs) // 3
        lo = st.mean([m for _, m in pairs[:t]])
        hi = st.mean([m for _, m in pairs[-t:]])
        sl, co = slope_corr(cost, mk)
        print(f"{cond:12s} {st.mean(mk):9.1f} +/- {st.pstdev(mk):4.1f} {sl:+14.2f} {co:+7.2f}"
              f"   {lo:5.1f} / {hi:5.1f}")
    print("\nRead: fixed markup -> slope~0, corr~0, lowcost==highcost. "
          "Competition -> markup varies with cost.")


if __name__ == "__main__":
    main()
