"""Raw per-round margin for ONE seed -- no averaging, no smoothing.

Each agent's margin (bid - cost) every round, one panel per condition, for a single seed.
Shows the real round-to-round texture the pooled/rolling-mean plots hide: how much the margin
actually bounces, whether A and B track each other, and the winner each round.

Usage:  python scripts/plot_margin_raw.py [--runs-root runs/v3] [--seed 0]
"""
from __future__ import annotations

import argparse
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
A_HUE, B_HUE, WIN_INK = "#0072B2", "#D55E00", "#1a1a1a"
INK, MUTED, GRID = "#1a1a1a", "#6b6b6b", "#d9d9d9"


def _style(ax, xlabel, ylabel, title):
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=6)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.6, linewidth=0.6)
    ax.set_axisbelow(True)


def main() -> None:
    p = argparse.ArgumentParser(description="Raw per-round margin for one seed (no averaging).")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "v3"))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "figures"))
    args = p.parse_args()
    runs_root = Path(args.runs_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(len(ORDER), 1, figsize=(11, 9), sharex=True)
    ymax = 0
    for ax, cond in zip(axes, ORDER):
        rs = RunLogger.load_rounds(runs_root / f"{cond}__seed{args.seed}")
        rounds = [r.round_number for r in rs]
        mA = [r.submissions[AgentId.A].bid - r.submissions[AgentId.A].cost for r in rs]
        mB = [r.submissions[AgentId.B].bid - r.submissions[AgentId.B].cost for r in rs]
        ax.plot(rounds, mA, color=A_HUE, linewidth=1.4, label="Agent A", zorder=2)
        ax.plot(rounds, mB, color=B_HUE, linewidth=1.4, label="Agent B", zorder=2)
        # mark the winning agent each round with a small dot on its own margin line
        for r, a, b in zip(rs, mA, mB):
            if r.winner is AgentId.A:
                ax.plot(r.round_number, a, "o", ms=3.2, color=A_HUE, zorder=3)
            elif r.winner is AgentId.B:
                ax.plot(r.round_number, b, "o", ms=3.2, color=B_HUE, zorder=3)
        ymax = max(ymax, max(mA + mB))
        _style(ax, "", "margin  (bid − cost),  $", f"{cond}   (seed {args.seed})")
    axes[0].legend(frameon=False, labelcolor=INK, loc="upper right", ncol=2, fontsize=9)
    axes[-1].set_xlabel("Round", color=INK)
    for ax in axes:
        ax.set_ylim(0, ymax * 1.05)          # shared y-scale so panels are comparable
    fig.suptitle(f"Per-round margin, no averaging — seed {args.seed} "
                 "(dots = round winner)", color=INK, fontsize=12, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path = out / f"margin_raw_seed{args.seed}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
