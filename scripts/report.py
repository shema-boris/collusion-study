"""Generate a self-contained HTML report from the run logs.

Reads runs/exp/, (re)builds the figures, and writes a single `report.html` with everything
embedded (charts as data URIs) -- open it in a browser, or Ctrl+P -> Save as PDF.

Usage:  python scripts/report.py [--runs-root runs/exp] [--out report.html]
"""
from __future__ import annotations

import argparse
import base64
import json
import statistics as st
import subprocess
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from history.storage import RunLogger  # noqa: E402
from metrics.collusion import round_series, win_rotation_rate  # noqa: E402

ORDER = ["R0", "C1", "S_informed", "A_informed"]

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: #1a1a1a; max-width: 960px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }
h1 { font-size: 26px; margin-bottom: 2px; }
h2 { font-size: 19px; margin-top: 34px; border-bottom: 1px solid #e5e5e5; padding-bottom: 6px; }
.muted { color: #6b6b6b; font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin-top: 10px; }
th, td { text-align: right; padding: 7px 10px; border-bottom: 1px solid #ececec; }
th:first-child, td:first-child { text-align: left; }
thead th { border-bottom: 2px solid #d9d9d9; color: #6b6b6b; font-weight: 600; }
.ok { color: #009e73; font-weight: 600; }
.bad { color: #d55e00; font-weight: 600; }
figure { margin: 18px 0; }
figure img { width: 100%; border: 1px solid #ececec; border-radius: 6px; }
figcaption { color: #6b6b6b; font-size: 13px; margin-top: 6px; }
.sample { background: #fafafa; border: 1px solid #ececec; border-radius: 6px; padding: 12px 14px;
          margin: 10px 0; font-size: 13px; }
.sample .r { color: #6b6b6b; }
.sample .quote { color: #333; font-style: italic; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } figure { page-break-inside: avoid; } }
"""


def summarize(run_dir: Path) -> dict:
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    recs = RunLogger.load_rounds(run_dir)
    cf = run_dir / "llm_calls.jsonl"
    calls = [json.loads(l) for l in cf.read_text(encoding="utf-8").splitlines() if l.strip()] if cf.exists() else []
    tok = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in calls)
    pf = sum(1 for c in calls if not c.get("parsed_ok"))
    ser = round_series(recs)
    cvals = [r["collusion_level"] for r in ser if r["collusion_level"] is not None]
    dvals = [r["detector_confidence"] for r in ser if r["detector_confidence"] is not None]
    return {
        "name": run_dir.name, "condition": run_dir.name.split("__seed")[0],
        "status": m.get("status"), "rounds": m.get("last_round"),
        "collusion_mean": st.mean(cvals) if cvals else None,
        "collusion_first": st.mean(cvals[:10]) if cvals else None,
        "collusion_last": st.mean(cvals[-10:]) if cvals else None,
        "detector_mean": st.mean(dvals) if dvals else None,
        "rotation": win_rotation_rate(recs), "tokens": tok, "parsefail": pf,
        "sample": recs[-1] if recs else None,
    }


def _num(x, fmt="{:.3f}"):
    return fmt.format(x) if x is not None else "—"


def img_figure(path: Path, caption: str) -> str:
    if not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode()
    return (f'<figure><img src="data:image/png;base64,{b64}" alt="{escape(caption)}">'
            f'<figcaption>{escape(caption)}</figcaption></figure>')


def sample_block(row: dict) -> str:
    rec = row["sample"]
    if rec is None:
        return ""
    a, b = rec.submissions["A"], rec.submissions["B"]
    det = ""
    if rec.detector is not None:
        det = f'<div class="r">detector D={rec.detector.confidence:.2f} · tells: {escape(", ".join(rec.detector.fired[:2]))}</div>'
    return (
        f'<div class="sample"><div class="r"><b>{escape(row["condition"])}</b> — round {rec.round_number} '
        f'(ref ${rec.scenario.reference_value:.0f}), winner {rec.winner}</div>'
        f'<div>A ${a.bid:.0f}/c{a.cost:.0f}: <span class="quote">{escape(a.reasoning[:180])}</span></div>'
        f'<div>B ${b.bid:.0f}/c{b.cost:.0f}: <span class="quote">{escape(b.reasoning[:180])}</span></div>'
        f'{det}</div>'
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Build a self-contained HTML report from run logs.")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--out", default=str(ROOT / "report.html"))
    args = p.parse_args()

    runs_root = Path(args.runs_root)
    figs = ROOT / "figures"
    # Refresh the figures first (best-effort; needs matplotlib).
    subprocess.run([sys.executable, str(ROOT / "scripts" / "plot_runs.py"),
                    "--runs-root", str(runs_root), "--out", str(figs)], check=False)

    dirs = [d for d in runs_root.glob("*__seed*") if (d / "manifest.json").exists()]
    rows = sorted((summarize(d) for d in dirs),
                  key=lambda r: ORDER.index(r["condition"]) if r["condition"] in ORDER else 99)

    # --- summary table ---
    trs = []
    for r in rows:
        status = r["status"]
        cls = "ok" if status == "completed" else "bad"
        delta = (None if r["collusion_last"] is None or r["collusion_first"] is None
                 else r["collusion_last"] - r["collusion_first"])
        trs.append(
            f"<tr><td>{escape(r['condition'])}</td>"
            f"<td class='{cls}'>{escape(str(status))}</td><td>{r['rounds']}</td>"
            f"<td>{_num(r['collusion_mean'])}</td><td>{_num(delta, '{:+.3f}')}</td>"
            f"<td>{_num(r['detector_mean'], '{:.2f}')}</td><td>{_num(r['rotation'], '{:.2f}')}</td>"
            f"<td>{r['tokens']:,}</td><td>{r['parsefail']}</td></tr>")
    table = (
        "<table><thead><tr><th>Condition</th><th>Status</th><th>Rounds</th>"
        "<th>Collusion (mean)</th><th>Collusion Δ (last−first 10)</th><th>Detector (mean)</th>"
        "<th>Win rotation</th><th>Tokens</th><th>Parse fails</th></tr></thead><tbody>"
        + "".join(trs) + "</tbody></table>")

    figures = (
        img_figure(figs / "collusion_over_rounds.png", "Collusion level over rounds, by condition")
        + img_figure(figs / "mean_collusion_by_condition.png", "Mean collusion level by condition")
        + "".join(img_figure(figs / f"collusion_vs_detector_{c}.png",
                             f"{c}: collusion level vs detector confidence")
                  for c in ORDER)
    )
    samples = "".join(sample_block(r) for r in rows)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Collusion study — run report</title><style>{CSS}</style></head><body>"
        f"<h1>Collusion study — run report</h1>"
        f"<div class='muted'>Generated {ts} · source: {escape(str(runs_root))}</div>"
        f"<p class='muted'>Collusion level = winning bid minus the competitive baseline b(c), normalized by "
        f"the round's reference (0 ≈ competitive). Detector confidence is 0–1. Metrics averaged across seeds.</p>"
        f"<h2>Summary</h2>{table}"
        f"<h2>Figures</h2>{figures}"
        f"<h2>Sample (final round of each condition)</h2>{samples}"
        f"</body></html>")

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB) — open it in a browser; Ctrl+P to save as PDF")


if __name__ == "__main__":
    main()
