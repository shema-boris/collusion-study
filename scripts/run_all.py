"""Run all conditions (x seeds) for N rounds. Resumable and fault-tolerant.

Each (condition, seed) is its own run directory, so a crash or a single failed condition never
loses prior work -- re-run to resume. Examples:

    python scripts/run_all.py --rounds 100 --seeds 0
    python scripts/run_all.py --rounds 100 --seeds 0,1,2 --conditions C1,A_blind
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.runner import load_live_context, run  # noqa: E402
from core.state import CONDITIONS  # noqa: E402

ALL_CONDITIONS = ["R0", "C1", "S_blind", "S_informed", "A_blind", "A_informed"]


def main() -> None:
    p = argparse.ArgumentParser(description="Run all conditions x seeds of the collusion study.")
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--seeds", default="0", help="comma-separated, e.g. 0,1,2")
    p.add_argument("--conditions", default="all", help="'all' or comma-separated condition names")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--window", type=int, default=None, help="history window (default from config)")
    args = p.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")]
    conditions = ALL_CONDITIONS if args.conditions == "all" else args.conditions.split(",")
    config, clients = load_live_context()

    for seed in seeds:
        for name in conditions:
            print(f"=== {name}  seed={seed}  ({args.rounds} rounds) ===", flush=True)
            try:
                run_dir = run(condition=CONDITIONS[name], seed=seed, rounds=args.rounds,
                              clients=clients, config=config, runs_root=args.runs_root,
                              resume=True, window=args.window)
                print(f"  done -> {run_dir}", flush=True)
            except Exception as e:  # keep going; this run is marked 'failed' and can be resumed
                print(f"  FAILED ({name} seed={seed}): {e}", flush=True)

    print("all runs complete")


if __name__ == "__main__":
    main()
