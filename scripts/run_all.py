"""Run all conditions (x seeds) for N rounds. Resumable, fault-tolerant, and self-resuming.

Each (condition, seed) is its own run directory, so a crash or a single failed condition never
loses prior work. With --passes > 1, the whole sweep is retried (resuming each time) until every
condition reaches the target rounds or the passes run out -- useful for grinding through shared
rate limits without babysitting it. Examples:

    python scripts/run_all.py --rounds 400 --seeds 0
    python scripts/run_all.py --rounds 400 --seeds 0 --passes 50 --pass-wait 180
    python scripts/run_all.py --rounds 400 --conditions C1,A_informed
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.runner import load_live_context, run  # noqa: E402
from core.state import CONDITIONS  # noqa: E402
from history.storage import run_dir_name  # noqa: E402

ALL_CONDITIONS = ["R0", "C1", "S_informed", "A_informed"]


def _complete(runs_root: Path, name: str, seed: int, rounds: int) -> bool:
    mp = runs_root / run_dir_name(name, seed) / "manifest.json"
    if not mp.exists():
        return False
    m = json.loads(mp.read_text(encoding="utf-8"))
    return m.get("status") == "completed" and (m.get("last_round") or 0) >= rounds


def main() -> None:
    p = argparse.ArgumentParser(description="Run all conditions x seeds of the collusion study.")
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--seeds", default="0", help="comma-separated, e.g. 0,1,2")
    p.add_argument("--conditions", default="all", help="'all' or comma-separated condition names")
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--window", type=int, default=None, help="history window (default from config)")
    p.add_argument("--passes", type=int, default=1,
                   help="re-run (resuming) up to N times until all complete -- rides out rate limits")
    p.add_argument("--pass-wait", type=float, default=180,
                   help="seconds to wait between passes (default 180)")
    p.add_argument("--common-cost", action="store_true",
                   help="both agents get the SAME cost each round (symmetric; Bertrand benchmark)")
    p.add_argument("--quality-weight", type=float, default=None,
                   help="override auction.quality_weight (0 = pure lowest-bid; clean Bertrand test)")
    args = p.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")]
    conditions = ALL_CONDITIONS if args.conditions == "all" else args.conditions.split(",")
    runs_root = Path(args.runs_root)
    config, clients = load_live_context()
    if args.common_cost or args.quality_weight is not None:
        auction = {**config["auction"]}
        if args.common_cost:
            auction["common_cost"] = True
        if args.quality_weight is not None:
            auction["quality_weight"] = args.quality_weight
        config = {**config, "auction": auction}

    def pending():
        return [(s, n) for s in seeds for n in conditions if not _complete(runs_root, n, s, args.rounds)]

    for p_idx in range(1, args.passes + 1):
        todo = pending()
        if not todo:
            print("ALL CONDITIONS COMPLETE.")
            return
        print(f"=== PASS {p_idx}/{args.passes} -- {len(todo)} condition(s) left ===", flush=True)
        for seed, name in todo:
            print(f"--- {name}  seed={seed}  ({args.rounds} rounds) ---", flush=True)
            try:
                run(condition=CONDITIONS[name], seed=seed, rounds=args.rounds, clients=clients,
                    config=config, runs_root=runs_root, resume=True, window=args.window)
            except Exception as e:  # keep going; resume will retry it next pass
                print(f"  paused ({name} seed={seed}): {e}", flush=True)

        if not pending():
            print("ALL CONDITIONS COMPLETE.")
            return
        if p_idx < args.passes:
            print(f"still {len(pending())} left; waiting {args.pass_wait:.0f}s before next pass...",
                  flush=True)
            time.sleep(args.pass_wait)

    left = pending()
    print(f"done with {args.passes} passes; {len(left)} still incomplete: "
          f"{', '.join(f'{n}(seed{s})' for s, n in left)} -- re-run to continue.")


if __name__ == "__main__":
    main()
