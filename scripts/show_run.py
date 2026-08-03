"""Human-readable view of a run's logs -- see how the models performed (DESIGN.md §12).

Usage:  python scripts/show_run.py runs/demo/C1__seed0 [max_rounds]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.state import LLMCall, RoundRecord  # noqa: E402


def _short(text: str, n: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def main() -> None:
    run_dir = Path(sys.argv[1])
    max_rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    cond = manifest["condition"]
    print(f"Run: {run_dir.name}")
    print(f"  condition={cond['name']} (regime={cond['detector_regime']}, "
          f"visibility={cond['visibility']})  seed={manifest['seed']}")
    print(f"  status={manifest['status']}  rounds={manifest['last_round']}  "
          f"models={manifest.get('models')}")
    print("-" * 78)

    rounds = [RoundRecord.model_validate_json(ln)
              for ln in (run_dir / "rounds.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    for rec in rounds[:max_rounds]:
        scn = rec.scenario.title if rec.scenario else "-"
        print(f"Round {rec.round_number}  [{scn}]")
        for a in ("A", "B"):
            sub = rec.submissions[a]
            q = rec.judge.quality[a]
            profit = rec.profits.get(a, 0.0)
            mark = " <= winner" if rec.winner == a else ""
            print(f"  {a}: cost={sub.cost:.1f} bid={sub.bid:.1f} q={q:.1f} "
                  f"profit={profit:.1f}{mark}")
            print(f"     \"{_short(sub.reasoning)}\"")
        if rec.detector is not None:
            print(f"  detector D={rec.detector.confidence:.2f} tells={rec.detector.fired}")
    if len(rounds) > max_rounds:
        print(f"... ({len(rounds) - max_rounds} more rounds)")

    # Aggregate model stats from the LLM-call log.
    calls_path = run_dir / "llm_calls.jsonl"
    calls = [LLMCall.model_validate_json(ln)
             for ln in calls_path.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if calls_path.exists() else []
    pt = sum(c.prompt_tokens or 0 for c in calls)
    ct = sum(c.completion_tokens or 0 for c in calls)
    parse_fail = sum(1 for c in calls if not c.parsed_ok)
    transport_err = sum(1 for c in calls if c.error and not c.raw_response)
    print("-" * 78)
    print(f"LLM calls: {len(calls)}  prompt_tokens={pt}  completion_tokens={ct}")
    print(f"  parse failures={parse_fail}  transport errors={transport_err}")


if __name__ == "__main__":
    main()
