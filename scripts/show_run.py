"""Human-readable view of a run's logs -- see how the models performed (DESIGN.md §12).

Usage:  python scripts/show_run.py runs/exp/C1__seed0 [--limit N] [--full] [--prompts]

  --full     untruncated reasoning + the full scenario brief + detector reasoning
  --prompts  also print the exact prompts the agents received (system once, user per round)

The raw logs -- rounds.jsonl and llm_calls.jsonl -- ALWAYS contain the complete, untruncated
prompts and responses regardless of these flags.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.state import LLMCall, RoundRecord  # noqa: E402


def _fmt(text: str, n) -> str:
    text = " ".join(text.split())
    if n is None or len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in text.splitlines())


def main() -> None:
    p = argparse.ArgumentParser(description="Show a run's rounds and model stats.")
    p.add_argument("run_dir")
    p.add_argument("--limit", type=int, default=20, help="max rounds to print (default 20)")
    p.add_argument("--full", action="store_true", help="untruncated reasoning + full scenario brief")
    p.add_argument("--prompts", action="store_true", help="also print the exact agent prompts")
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    width = None if args.full else 100

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    cond = manifest["condition"]

    rounds = [RoundRecord.model_validate_json(ln)
              for ln in (run_dir / "rounds.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    calls_path = run_dir / "llm_calls.jsonl"
    calls = [LLMCall.model_validate_json(ln)
             for ln in calls_path.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if calls_path.exists() else []
    # index the first attempt of each (round, role) for prompt lookup
    prompt_by = {}
    for c in calls:
        prompt_by.setdefault((c.round_number, c.role), c)

    print(f"Run: {run_dir.name}")
    print(f"  condition={cond['name']} (regime={cond['detector_regime']}, "
          f"visibility={cond['visibility']})  seed={manifest['seed']}")
    print(f"  status={manifest['status']}  rounds={manifest['last_round']}  "
          f"models={manifest.get('models')}")

    if args.prompts:
        sys_prompt = next((c.request.get("system") for c in calls
                           if c.role.startswith("agent") and c.request.get("system")), None)
        if sys_prompt:
            print("\n=== AGENT SYSTEM PROMPT (identical every round) ===")
            print(_indent(sys_prompt))
    print("-" * 78)

    for rec in rounds[:args.limit]:
        scn = rec.scenario.title if rec.scenario else "-"
        ref = f"  ref=${rec.scenario.reference_value:.0f}" if rec.scenario else ""
        print(f"Round {rec.round_number}  [{scn}]{ref}")
        if args.full and rec.scenario is not None:
            print("  Scenario brief:")
            print(_indent(rec.scenario.render(), "    "))
            print(f"    [economics] reference=${rec.scenario.reference_value:.0f}  "
                  f"cost_range=[{rec.scenario.cost_low:.0f},{rec.scenario.cost_high:.0f}]")
        if args.prompts:
            call = prompt_by.get((rec.round_number, "agent_A"))
            if call:
                print("  Agent A user prompt (exact input, incl. the history it saw):")
                print(_indent(call.request.get("user", ""), "    "))
        for a in ("A", "B"):
            sub = rec.submissions[a]
            q = rec.judge.quality[a]
            profit = rec.profits.get(a, 0.0)
            mark = " <= winner" if rec.winner == a else ""
            print(f"  {a}: cost={sub.cost:.1f} bid={sub.bid:.1f} q={q:.1f} profit={profit:.1f}{mark}")
            print(f"     {_fmt(sub.reasoning, width)}")
        if rec.detector is not None:
            print(f"  detector D={rec.detector.confidence:.2f} tells={rec.detector.fired}")
            if args.full and rec.detector.reasoning:
                print(f"     detector reasoning: {rec.detector.reasoning}")
    if len(rounds) > args.limit:
        print(f"... ({len(rounds) - args.limit} more rounds; raise --limit to see more)")

    pt = sum(c.prompt_tokens or 0 for c in calls)
    ct = sum(c.completion_tokens or 0 for c in calls)
    parse_fail = sum(1 for c in calls if not c.parsed_ok)
    transport_err = sum(1 for c in calls if c.error and not c.raw_response)
    print("-" * 78)
    print(f"LLM calls: {len(calls)}  prompt_tokens={pt}  completion_tokens={ct}")
    print(f"  parse failures={parse_fail}  transport errors={transport_err}")


if __name__ == "__main__":
    main()
