"""Structural-collusion figures (the v3 headline findings).

Three figures, written to figures/:
  1. structure_cost_response.png -- actual markup vs the Bayes-Nash competitive markup, per
     condition. R0 tracks it (cost-responsive competition); the history cells go flat
     (cost-insensitive fixed markup). The structural signature.
  2. structure_markup_over_rounds.png -- mean markup per round. R0 stays high; the history
     cells sit low and settle -- convergence emerges only with a shared record.
  3. structure_null_and_falsepos.png -- (L) price above competitive ~0 everywhere (no
     supra-competitive pricing) yet (R) the detector flags the informed cells at ~0.7.

Design (dataviz): Okabe-Ito colorblind-safe palette in fixed condition order (identity, never
cycled), single y-axis per panel, recessive grid, neutral-ink text, direct line labels.

Usage:  python scripts/plot_structure.py [--runs-root runs/v3] [--out figures]
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
from metrics.collusion import collusion_level  # noqa: E402

ORDER = ["R0", "C1", "S_informed", "A_informed"]
LABEL = {"R0": "R0 (no history)", "C1": "C1 (history)",
         "S_informed": "S_informed", "A_informed": "A_informed"}
COLOR = {"R0": "#000000", "C1": "#E69F00", "S_informed": "#009E73", "A_informed": "#D55E00"}
INK, MUTED, GRID = "#1a1a1a", "#6b6b6b", "#d9d9d9"
SEEDS = (0, 1, 2)


def _style(ax, xlabel, ylabel, title):
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=8)
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, alpha=0.6, linewidth=0.6)
    ax.set_axisbelow(True)


def load(runs_root, cond, seed):
    return list(RunLogger.load_rounds(runs_root / f"{cond}__seed{seed}"))


def _ols_slope(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def fig_cost_response(runs_root, out):
    """2x2 small multiples: actual markup vs competitive (Bayes-Nash) markup, all seeds+agents."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharex=True, sharey=True)
    for ax, cond in zip(axes.flat, ORDER):
        act, comp = [], []
        for s in SEEDS:
            for r in load(runs_root, cond, s):
                ch = r.scenario.cost_high
                for a in (AgentId.A, AgentId.B):
                    sub = r.submissions[a]
                    act.append(sub.bid - sub.cost)
                    comp.append((ch - sub.cost) / 2)
        ax.scatter(comp, act, s=9, color=COLOR[cond], alpha=0.22, edgecolors="none")
        lo, hi = 0, max(max(act), max(comp)) * 1.02
        ax.plot([lo, hi], [lo, hi], color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)),
                zorder=1)                                   # y = x: pure competition
        slope = _ols_slope(comp, act)
        xs = [min(comp), max(comp)]
        b0 = st.mean(act) - slope * st.mean(comp)
        ax.plot(xs, [slope * x + b0 for x in xs], color=COLOR[cond], linewidth=2.2, zorder=3)
        ax.text(0.04, 0.94, f"{LABEL[cond]}\nslope = {slope:.2f}", transform=ax.transAxes,
                va="top", ha="left", color=INK, fontsize=11,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID, alpha=0.85))
        _style(ax, "Competitive markup  (cost_high − cost)/2,  $",
               "Actual markup  (bid − cost),  $", "")
    fig.suptitle("Shared history flattens the bid–cost relationship "
                 "(slope 1 = cost-responsive competition; slope 0 = fixed markup)",
                 color=INK, fontsize=12, x=0.02, ha="left")
    fig.text(0.5, 0.005, "Dashed line = pure Bayes–Nash competition (y = x). "
             "R0 runs parallel to it; the history cells collapse toward flat.",
             ha="center", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(out / "structure_cost_response.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _smooth(ys, w=5):
    out = []
    for i in range(len(ys)):
        lo = max(0, i - w + 1)
        out.append(sum(ys[lo:i + 1]) / (i - lo + 1))
    return out


def fig_markup_over_rounds(runs_root, out):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for cond in ORDER:
        n_rounds = 80
        per_round = [[] for _ in range(n_rounds)]
        for s in SEEDS:
            rs = load(runs_root, cond, s)
            for i, r in enumerate(rs[:n_rounds]):
                for a in (AgentId.A, AgentId.B):
                    per_round[i].append(r.submissions[a].bid - r.submissions[a].cost)
        xs = [i + 1 for i in range(n_rounds) if per_round[i]]
        ys = _smooth([st.mean(per_round[i]) for i in range(n_rounds) if per_round[i]])
        ax.plot(xs, ys, color=COLOR[cond], linewidth=2.2, zorder=3, label=LABEL[cond])
    ax.set_xlim(1, 80)
    # Three history lines overlap (that IS the finding), so identity goes to a legend, not
    # colliding end-labels; R0 is the one clearly separated line up top.
    ax.legend(frameon=False, labelcolor=INK, loc="upper right", ncol=2, fontsize=9)
    _style(ax, "Round", "Mean markup  (bid − cost),  $  [5-round rolling mean]",
           "Markup over rounds: history compresses margins and settles; R0 stays high")
    fig.savefig(out / "structure_markup_over_rounds.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_null_and_falsepos(runs_root, out):
    coll_m, coll_e, det_m, det_e = {}, {}, {}, {}
    for cond in ORDER:
        per_seed_coll, per_seed_det = [], []
        for s in SEEDS:
            rs = load(runs_root, cond, s)
            cvals = [collusion_level(r) for r in rs if collusion_level(r) is not None]
            dvals = [r.detector.confidence for r in rs if r.detector is not None]
            per_seed_coll.append(st.mean(cvals))
            if dvals:
                per_seed_det.append(st.mean(dvals))
        coll_m[cond] = st.mean(per_seed_coll)
        coll_e[cond] = st.pstdev(per_seed_coll)
        if per_seed_det:
            det_m[cond] = st.mean(per_seed_det)
            det_e[cond] = st.pstdev(per_seed_det)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.6))
    conds = ORDER
    axL.bar(range(len(conds)), [coll_m[c] for c in conds],
            yerr=[coll_e[c] for c in conds], width=0.62,
            color=[COLOR[c] for c in conds], capsize=4,
            error_kw=dict(ecolor=MUTED, lw=1))
    axL.axhline(0, color=MUTED, lw=1)
    axL.set_xticks(range(len(conds)))
    axL.set_xticklabels([LABEL[c] for c in conds], rotation=18, ha="right", fontsize=9)
    _style(axL, "", "Price above competitive  (÷ reference)",
           "Monitored cells price at competitive (≈0), not above it")

    dconds = [c for c in conds if c in det_m]
    axR.bar(range(len(dconds)), [det_m[c] for c in dconds],
            yerr=[det_e[c] for c in dconds], width=0.5,
            color=[COLOR[c] for c in dconds], capsize=4, error_kw=dict(ecolor=MUTED, lw=1))
    axR.set_ylim(0, 1)
    axR.set_xticks(range(len(dconds)))
    axR.set_xticklabels([LABEL[c] for c in dconds], fontsize=9)
    _style(axR, "", "Mean detector confidence  D",
           "…yet the detector flags the informed cells at ~0.7  (false positives)")
    fig.tight_layout()
    fig.savefig(out / "structure_null_and_falsepos.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="Structural-collusion figures from run logs.")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "v3"))
    p.add_argument("--out", default=str(ROOT / "figures"))
    args = p.parse_args()
    runs_root = Path(args.runs_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fig_cost_response(runs_root, out)
    fig_markup_over_rounds(runs_root, out)
    fig_null_and_falsepos(runs_root, out)
    print(f"wrote 3 figures to {out}/ : structure_cost_response, "
          f"structure_markup_over_rounds, structure_null_and_falsepos")


if __name__ == "__main__":
    main()
