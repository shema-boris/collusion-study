"""Generate the core figures from run logs (DESIGN.md §9).

Reads runs/<experiment>/<condition>__seed*/ and writes PNGs to figures/. Metrics are averaged
across seeds per round. Design (dataviz): line charts for change-over-time, a single 0-1 y-axis
(collusion level and detector confidence are both fractions -- no dual axis), the Okabe-Ito
colorblind-safe palette in a fixed condition order, recessive grid, neutral-ink text.

Usage:  python scripts/plot_runs.py [--runs-root runs/exp] [--out figures]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless: render straight to PNG
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from history.storage import RunLogger  # noqa: E402
from metrics.collusion import round_series  # noqa: E402

# Fixed condition order + Okabe-Ito colorblind-safe hues (assigned by identity, never cycled).
ORDER = ["R0", "C1", "S_blind", "S_informed", "A_blind", "A_informed"]
COLOR = {
    "R0": "#000000", "C1": "#E69F00", "S_blind": "#56B4E9",
    "S_informed": "#009E73", "A_blind": "#0072B2", "A_informed": "#D55E00",
}
COLLUSION_HUE, DETECTOR_HUE = "#0072B2", "#D55E00"
INK, MUTED, GRID = "#1a1a1a", "#6b6b6b", "#d9d9d9"


def _style(ax, xlabel: str, ylabel: str, title: str) -> None:
    ax.set_title(title, color=INK, fontsize=12, loc="left", pad=10)
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.6, linewidth=0.6)
    ax.set_axisbelow(True)


def discover(runs_root: Path) -> dict[str, list[Path]]:
    runs: dict[str, list[Path]] = defaultdict(list)
    for d in sorted(runs_root.glob("*__seed*")):
        if (d / "rounds.jsonl").exists():
            runs[d.name.split("__seed")[0]].append(d)
    return runs


def metric_by_round(run_dirs: list[Path], key: str) -> tuple[list[int], list[float]]:
    """Mean of `key` across seeds, per round (skipping None)."""
    per_round: dict[int, list[float]] = defaultdict(list)
    for d in run_dirs:
        for row in round_series(RunLogger.load_rounds(d)):
            if row[key] is not None:
                per_round[row["round"]].append(row[key])
    rounds = sorted(per_round)
    return rounds, [sum(per_round[r]) / len(per_round[r]) for r in rounds]


def fig_collusion_over_rounds(runs, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    n = 0
    for cond in ORDER:
        if cond in runs:
            xs, ys = metric_by_round(runs[cond], "collusion_level")
            if xs:
                ax.plot(xs, ys, color=COLOR[cond], linewidth=2, label=cond)
                n += 1
    if n:
        ax.legend(frameon=False, labelcolor=INK)
    _style(ax, "Round", "Collusion level  (price above competitive / reference)",
           "Collusion level over rounds, by condition")
    fig.savefig(out / "collusion_over_rounds.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_collusion_vs_detector(run_dirs, cond: str, out: Path) -> bool:
    xc, yc = metric_by_round(run_dirs, "collusion_level")
    xd, yd = metric_by_round(run_dirs, "detector_confidence")
    if not xd:
        return False  # no detector in this condition
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(xc, yc, color=COLLUSION_HUE, linewidth=2, label="Collusion level")
    ax.plot(xd, yd, color=DETECTOR_HUE, linewidth=2, label="Detector confidence")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, labelcolor=INK)
    _style(ax, "Round", "Fraction (0-1)",
           f"{cond}: collusion vs detector confidence  (do the lines cross?)")
    fig.savefig(out / f"collusion_vs_detector_{cond}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


def fig_mean_collusion_bar(runs, out: Path) -> None:
    conds = [c for c in ORDER if c in runs]
    means = []
    for c in conds:
        _, ys = metric_by_round(runs[c], "collusion_level")
        means.append(sum(ys) / len(ys) if ys else 0.0)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(conds, means, color=[COLOR[c] for c in conds], width=0.62)
    _style(ax, "Condition", "Mean collusion level", "Mean collusion level by condition")
    fig.savefig(out / "mean_collusion_by_condition.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="Plot core figures from run logs.")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--out", default=str(ROOT / "figures"))
    args = p.parse_args()

    runs = discover(Path(args.runs_root))
    if not runs:
        print(f"no runs found under {args.runs_root}")
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fig_collusion_over_rounds(runs, out)
    fig_mean_collusion_bar(runs, out)
    crossed = [c for c in ORDER if c in runs and fig_collusion_vs_detector(runs[c], c, out)]

    print(f"runs: {', '.join(f'{c}(x{len(runs[c])})' for c in ORDER if c in runs)}")
    print(f"wrote figures to {out}/ : collusion_over_rounds, mean_collusion_by_condition"
          + (f", collusion_vs_detector_{{{','.join(crossed)}}}" if crossed else ""))


if __name__ == "__main__":
    main()
