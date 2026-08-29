"""Executes one configured experiment (protocol Section 12 runner).

One round is: render each agent's observation from the SAME completed-round history -> both agents
bid independently (neither sees the other's current bid, Section 6 boundary) -> allocate + payoff
(Section 4) -> regulator if Study 2 (Section 9) -> log. The runner discovers behavior; it never
labels a round collusive and never nudges a price (Section 7, Section 14).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from study.agents import decide_bid, make_client
from study.config import Conditions, Regulation, StudyConfig
from study.environment import allocate, clamp_bid
from study.prompts import observation_prompt, system_prompt
from study.regulator import Regulator, joint_average, rolling_average
from study.runlog import RoundRecord, RunLogger, load_rounds, phase_of

ROUND_RETRIES = 3


def _manifest(config: StudyConfig) -> dict:
    return {
        "study": config.study,
        "condition": config.condition_name,
        "conditions": asdict(config.conditions),
        "regulation": asdict(config.regulation) if config.regulation else None,
        "market": {"cost": config.cost, "demand": config.demand,
                   "price_min": config.price_min, "price_max": config.price_max},
        "horizon": config.horizon,
        "models": {"A": config.model_a, "B": config.model_b},
        "temperature": config.temperature, "max_tokens": config.max_tokens,
        "seed": config.seed, "status": "running", "last_round": 0,
    }


def _bid_for(client, config, agent, round_number, history, logger) -> tuple[float, str]:
    """Get one agent's bid for this round, retrying on failure, with a logged fallback."""
    system = system_prompt(agent)
    obs = observation_prompt(round_number, history, agent, config.conditions)
    rec = None
    for _ in range(ROUND_RETRIES):
        rec = decide_bid(client, system=system, observation=obs, round_number=round_number,
                         agent=agent, seed=config.seed, price_min=config.price_min,
                         price_max=config.price_max)
        logger.log_llm_call(rec)
        if rec["parse_ok"] and rec["bid"] is not None:
            return rec["bid"], rec["reasoning"]
    # Persistent failure: fall back to this agent's most recent own bid, else the price ceiling.
    prior_own = [h["bids"][agent] for h in history]
    fallback = prior_own[-1] if prior_own else config.price_max
    logger.log_llm_call({**(rec or {}), "agent": agent, "round": round_number,
                         "bid": fallback, "parse_ok": False, "error": "fallback_used"})
    return clamp_bid(fallback, price_min=config.price_min, price_max=config.price_max), ""


def run(config: StudyConfig, run_dir: str | Path, *, resume: bool = False,
        clients: Optional[dict] = None) -> Path:
    run_dir = Path(run_dir)
    if clients is None:   # injectable for tests (stub transport); built live otherwise
        clients = {"A": make_client(config.model_a, temperature=config.temperature, max_tokens=config.max_tokens),
                   "B": make_client(config.model_b, temperature=config.temperature, max_tokens=config.max_tokens)}
    manifest = _manifest(config)
    if resume and (run_dir / "rounds.jsonl").exists():
        logger, history = RunLogger.resume(run_dir, manifest)
    else:
        logger, history = RunLogger.create(run_dir, manifest), []

    cumulative = {"A": 0.0, "B": 0.0}
    for h in history:
        for a in ("A", "B"):
            cumulative[a] = h["cumulative_profit"][a]
    joint_hist = [h["joint_average"] for h in history]
    regulator = Regulator(config.regulation) if config.regulation else None

    start = len(history) + 1
    try:
        for t in range(start, config.horizon + 1):
            # Both observations built from the SAME completed history BEFORE either agent bids.
            bid_a, reason_a = _bid_for(clients["A"], config, "A", t, history, logger)
            bid_b, reason_b = _bid_for(clients["B"], config, "B", t, history, logger)

            alloc = allocate(bid_a, bid_b, cost=config.cost, demand=config.demand)
            m_t = joint_average(bid_a, bid_b)
            joint_hist.append(m_t)

            if regulator is not None:
                r_t = rolling_average(joint_hist, config.regulation.window)
                detected = regulator.detected(r_t)
                net, pen_amt, pen_status = regulator.apply(alloc.gross_profit, detected)
            else:                                   # Study 1: no detector, no penalty (Section 2)
                r_t = rolling_average(joint_hist, 5)   # informational only
                detected = False
                net = dict(alloc.gross_profit)
                pen_amt = {"A": 0.0, "B": 0.0}
                pen_status = {"A": False, "B": False}

            for a in ("A", "B"):
                cumulative[a] += net[a]

            rec = RoundRecord(
                round_number=t, phase=phase_of(t, config.horizon),
                bids={"A": bid_a, "B": bid_b}, winner=alloc.winner, units=dict(alloc.units),
                gross_profit=dict(alloc.gross_profit), penalty_status=pen_status,
                penalty_amount=pen_amt, net_profit=net, cumulative_profit=dict(cumulative),
                joint_average=m_t, rolling_average=r_t, detected=detected,
                reasoning={"A": reason_a, "B": reason_b})
            logger.log_round(rec)
            logger.update_manifest(last_round=t)
            history.append(asdict(rec))
        logger.update_manifest(status="completed")
    finally:
        logger.close()
    return run_dir


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Run one Study 1/2 reverse-auction experiment.")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--study", choices=["study1", "study2"], default="study1")
    p.add_argument("--rounds", type=int, default=60)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--model-a", default="qwen/qwen-2.5-72b-instruct")
    p.add_argument("--model-b", default="qwen/qwen-2.5-72b-instruct")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--history", dest="history", action="store_true", default=True)
    p.add_argument("--no-history", dest="history", action="store_false")
    p.add_argument("--show-rival-reasoning", action="store_true",
                   help="expose the rival's PRIOR reasoning text (an explicit condition, Section 6)")
    p.add_argument("--condition-name", default=None)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)

    conds = Conditions(history=args.history, show_rival_reasoning=args.show_rival_reasoning)
    name = args.condition_name or (
        f"{'history' if args.history else 'nohistory'}_"
        f"{'visible' if args.show_rival_reasoning else 'hidden'}_reasoning")
    config = StudyConfig(
        horizon=args.rounds, study=args.study, condition_name=name, conditions=conds,
        regulation=Regulation() if args.study == "study2" else None,
        model_a=args.model_a, model_b=args.model_b, temperature=args.temperature, seed=args.seed)
    out = run(config, args.run_dir, resume=args.resume)
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
