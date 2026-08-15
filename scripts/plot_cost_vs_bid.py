"""Cost vs bid scatter -- the raw bidding trend, both agents on one chart per condition.

2x2 small multiples (one per condition). Each panel plots every round's (cost, bid) for Agent A
and Agent B in two colors, a y = x reference (bid = cost, the break-even line), and an OLS fit
with its slope. Both agents share the panel, so you can see whether A and B bid alike.

CAVEAT: contracts vary in size (cost_high/reference differ per round), and bigger contracts have
both higher costs and higher bids -- so the cost->bid slope mostly reflects contract size, not
strategy. For the strategy question (does markup respond to cost?) see plot_structure.py.

Usage:  python scripts/plot_cost_vs_bid.py [--runs-root runs/v3] [--seeds 0,1,2]
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.state import AgentId  # noqa: E402
from history.storage import RunLogger  # noqa: E402

ORDER = ["R0", "C1", "S_informed", "A_informed"]
LABEL = {"R0": "R0 (no history)", "C1": "C1 (history)",
         "S_informed": "S_informed", "A_informed": "A_informed"}
A_HUE, B_HUE = "#0072B2", "#D55E00"
INK, MUTED, GRID = "#1a1a1a", "#6b6b6b", "#d9d9d9"


def _style(ax, xlabel, ylabel, title):
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=6)
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.6, linewidth=0.6)
    ax.set_axisbelow(True)


def _ols(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def main() -> None:
    p = argparse.ArgumentParser(description="Cost vs bid scatter, both agents, per condition.")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "v3"))
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--out", default=str(ROOT / "figures"))
    args = p.parse_args()
    runs_root = Path(args.runs_root)
    seeds = [int(s) for s in args.seeds.split(",")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(11, 9), sharex=True, sharey=True)
    hi = 0
    for ax, cond in zip(axes.flat, ORDER):
        cA = cB = None
        costA, bidA, costB, bidB = [], [], [], []
        for s in seeds:
            for r in RunLogger.load_rounds(runs_root / f"{cond}__seed{s}"):
                costA.append(r.submissions[AgentId.A].cost); bidA.append(r.submissions[AgentId.A].bid)
                costB.append(r.submissions[AgentId.B].cost); bidB.append(r.submissions[AgentId.B].bid)
        ax.scatter(costA, bidA, s=13, color=A_HUE, alpha=0.30, edgecolors="none", label="Agent A")
        ax.scatter(costB, bidB, s=13, color=B_HUE, alpha=0.30, edgecolors="none", label="Agent B")
        allc = costA + costB; allb = bidA + bidB
        hi = max(hi, max(allc + allb))
        lo = min(allc + allb)
        ax.plot([lo, max(allc + allb)], [lo, max(allc + allb)],
                color=MUTED, linewidth=1.1, linestyle=(0, (4, 3)), zorder=1)  # y = x (break-even)
        slope, intercept = _ols(allc, allb)
        xs = [min(allc), max(allc)]
        ax.plot(xs, [slope * x + intercept for x in xs], color=INK, linewidth=2, zorder=3)
        ax.text(0.04, 0.94, f"{LABEL[cond]}\nbid = {slope:.2f}·cost + {intercept:.0f}",
                transform=ax.transAxes, va="top", ha="left", color=INK, fontsize=10,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID, alpha=0.85))
        _style(ax, "Cost,  $", "Bid,  $", "")
    axes.flat[0].legend(frameon=False, labelcolor=INK, loc="lower right", fontsize=9)
    fig.suptitle("Cost vs bid, per condition (dashed = break-even bid = cost; solid = fitted trend)",
                 color=INK, fontsize=12, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    path = out / "cost_vs_bid.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
