"""Executes one configured experiment (protocol Section 12 runner).

One round is: render each agent's observation from the SAME completed-round history -> both agents
bid independently (neither sees the other's current bid, Section 6 boundary) -> allocate + payoff
(Section 4) -> regulator if Study 2 (Section 9) -> log. The runner discovers behavior; it never
labels a round collusive and never nudges a price (Section 7, Section 14).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional


def _load_env() -> None:
    """Load .env into os.environ. Uses python-dotenv if present, else a minimal parser -- so the
    key loads even in a venv that lacks python-dotenv (which otherwise causes a 401 'Missing
    Authentication header' because OPENROUTER_API_KEY never reaches the client)."""
    import os
    env_path = Path(__file__).resolve().parents[1] / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass
    if not os.environ.get("OPENROUTER_API_KEY") and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from study.agents import decide_bid, make_client
from study.config import Conditions, Regulation, StudyConfig
from study.detector import DetectorFailure, assess_round
from study.detector_prompts import DETECTOR_PROMPT_VERSION
from study.environment import allocate, allocate_smooth
from study.prehistory import near_cost_history
from study.prompts import observation_prompt, system_prompt
from study.regulator import Regulator, joint_average, rolling_average
from study.runlog import RoundRecord, RunLogger, load_prehistory, load_rounds, phase_of

ROUND_RETRIES = 3


class AgentFailure(RuntimeError):
    """Raised when an agent cannot return a valid bid after all retries."""


def _print_synthetic_history(rounds: list[dict]) -> None:
    print("\n=== SYNTHETIC PREHISTORY (agent-visible context) ===")
    for rec in rounds:
        print(f"\n--- Synthetic round {rec['round_number']} ---")
        print(f"Alpha bid: ${rec['bids']['A']:.2f}")
        print(f"Beta bid: ${rec['bids']['B']:.2f}")
        print(f"Units A/B: {rec['units']['A']} / {rec['units']['B']}")
        print(
            f"Round profit A/B: ${rec['net_profit']['A']:.2f} / "
            f"${rec['net_profit']['B']:.2f}"
        )
        print(
            f"Cumulative profit A/B: ${rec['cumulative_profit']['A']:.2f} / "
            f"${rec['cumulative_profit']['B']:.2f}"
        )
    print("\n=== LIVE MODEL ROUNDS BEGIN ===", flush=True)


def _manifest(config: StudyConfig, prehistory: Optional[list[dict]] = None) -> dict:
    return {
        "study": config.study,
        "condition": config.condition_name,
        "conditions": asdict(config.conditions),
        "regulation": asdict(config.regulation) if config.regulation else None,
        "market": {"cost": config.cost, "demand": config.demand,
                   "price_min": config.price_min, "price_max": config.price_max,
                   "type": config.market_type,
                   "reservation_value": config.reservation_value,
                   "allocation_sensitivity": config.allocation_sensitivity},
        "private_memory": config.private_memory,
        "prompt_variant": config.prompt_variant,
        "explore_strategies": config.explore_strategies,
        "winner_p1": config.winner_p1,
        "history_window": config.history_window,
        "horizon": config.horizon,
        "models": {"A": config.model_a, "B": config.model_b},
        "temperature": config.temperature, "max_tokens": config.max_tokens,
        "detector_design": {
            "primary_evidence": "stated_reasoning_plans_insights",
            "bids_role": "context_only",
            "decision_rule": "reasoning_mutual_v1",
            "prompt_version": DETECTOR_PROMPT_VERSION,
            "failure_policy": "stop_run",
        } if config.regulation and config.regulation.mode == "llm_reasoning" else None,
        "prehistory": {
            "kind": "synthetic_near_cost",
            "rounds": len(prehistory),
            "stored_in": "prehistory.json",
            "excluded_from_analysis": True,
        } if prehistory else None,
        "seed": config.seed, "status": "running", "last_round": 0,
    }


def _bid_for(client, config, agent, round_number, history, logger,
             private_memory: Optional[dict] = None) -> tuple[float, str, str, str]:
    """Get one valid agent bid or stop the run without manufacturing an action."""
    system = system_prompt(agent, market_type=config.market_type,
                           private_memory=config.private_memory,
                           reservation_value=config.reservation_value,
                           allocation_sensitivity=config.allocation_sensitivity,
                           prompt_variant=config.prompt_variant,
                           explore_strategies=config.explore_strategies,
                           winner_p1=config.winner_p1)
    visible_history = history[-config.history_window:] if config.history_window else history
    obs = observation_prompt(round_number, visible_history, agent, config.conditions,
                             market_type=config.market_type,
                             private_memory=private_memory if config.private_memory else None)
    rec = None
    for _ in range(ROUND_RETRIES):
        rec = decide_bid(client, system=system, observation=obs, round_number=round_number,
                         agent=agent, seed=config.seed, price_min=config.price_min,
                         price_max=config.price_max)
        logger.log_llm_call(rec)
        if rec["parse_ok"] and rec["bid"] is not None:
            return rec["bid"], rec["reasoning"], rec.get("plan", ""), rec.get("insights", "")
    logger.log_llm_call({**(rec or {}), "agent": agent, "round": round_number,
                         "parse_ok": False, "error": "agent_response_invalid"})
    raise AgentFailure(
        f"agent {agent} failed to return a valid bid in round {round_number}")


def _validate_resume_manifest(run_dir: Path, expected: dict) -> None:
    """Reject accidental cross-condition resumes while allowing horizon extension."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return
    import json
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    immutable = (
        "study", "condition", "conditions", "regulation", "market", "private_memory",
        "prompt_variant", "explore_strategies", "winner_p1", "history_window", "models",
        "temperature", "max_tokens", "detector_design", "prehistory", "seed",
    )
    changed = [key for key in immutable if stored.get(key) != expected.get(key)]
    if changed:
        raise ValueError(
            "resume configuration differs from the stored manifest: " + ", ".join(changed))


def run(config: StudyConfig, run_dir: str | Path, *, resume: bool = False,
        clients: Optional[dict] = None, prehistory: Optional[list[dict]] = None) -> Path:
    run_dir = Path(run_dir)
    if clients is None:   # injectable for tests (stub transport); built live otherwise
        clients = {"A": make_client(config.model_a, temperature=config.temperature, max_tokens=config.max_tokens),
                   "B": make_client(config.model_b, temperature=config.temperature, max_tokens=config.max_tokens)}
        if config.regulation and config.regulation.mode == "llm_reasoning":
            clients["detector"] = make_client(
                config.regulation.detector_model, temperature=0.0,
                max_tokens=config.regulation.detector_max_tokens)
    if resume and (run_dir / "rounds.jsonl").exists():
        stored_prehistory = load_prehistory(run_dir)
        if prehistory is not None and prehistory != stored_prehistory:
            raise ValueError("supplied prehistory does not match the stored run prehistory")
        prehistory = stored_prehistory
        manifest = _manifest(config, prehistory)
        _validate_resume_manifest(run_dir, manifest)
        logger, history = RunLogger.resume(run_dir, manifest)
    else:
        prehistory = list(prehistory or [])
        manifest = _manifest(config, prehistory)
        logger, history = RunLogger.create(run_dir, manifest), []
        if prehistory:
            logger.write_prehistory(prehistory)
            _print_synthetic_history(prehistory)

    # Synthetic context is visible to agents but kept out of rounds.jsonl and analysis.
    observed_history = list(prehistory) + history

    cumulative = {"A": 0.0, "B": 0.0}
    for h in observed_history:
        for a in ("A", "B"):
            cumulative[a] = h["cumulative_profit"][a]
    joint_hist = [h["joint_average"] for h in observed_history]
    regulator = Regulator(config.regulation) if config.regulation else None
    memories = {"A": {"plan": "", "insights": ""},
                "B": {"plan": "", "insights": ""}}
    if config.private_memory and history:
        last = history[-1]
        for agent in ("A", "B"):
            memories[agent] = {"plan": (last.get("plans") or {}).get(agent, ""),
                               "insights": (last.get("insights") or {}).get(agent, "")}

    prehistory_count = len(prehistory)
    start = prehistory_count + len(history) + 1
    end = prehistory_count + config.horizon
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bidder")
    try:
        for t in range(start, end + 1):
            # Both observations built from the SAME completed history BEFORE either agent bids.
            future_a = pool.submit(_bid_for, clients["A"], config, "A", t,
                                   observed_history, logger, memories["A"])
            future_b = pool.submit(_bid_for, clients["B"], config, "B", t,
                                   observed_history, logger, memories["B"])
            bid_a, reason_a, plan_a, insights_a = future_a.result()
            bid_b, reason_b, plan_b, insights_b = future_b.result()

            if config.market_type == "smooth_procurement":
                alloc = allocate_smooth(
                    bid_a, bid_b, cost=config.cost, demand=config.demand,
                    reservation_value=config.reservation_value,
                    sensitivity=config.allocation_sensitivity)
            else:
                alloc = allocate(bid_a, bid_b, cost=config.cost, demand=config.demand)
            m_t = joint_average(bid_a, bid_b)
            joint_hist.append(m_t)

            detector_assessment = None
            if regulator is not None and config.regulation.mode == "llm_reasoning":
                current_for_detector = {
                    "bids": {"A": bid_a, "B": bid_b},
                    "units": dict(alloc.units),
                    "gross_profit": dict(alloc.gross_profit),
                    "agents": {
                        "A": {"reasoning": reason_a, "plan": plan_a, "insights": insights_a},
                        "B": {"reasoning": reason_b, "plan": plan_b, "insights": insights_b},
                    },
                }
                detector_history = observed_history[-config.regulation.detector_history_window:]
                detector_assessment = assess_round(
                    clients["detector"], market_type=config.market_type, round_number=t,
                    current=current_for_detector, history=detector_history, seed=config.seed,
                    logger=logger)
                detected = detector_assessment["detected"]
                r_t = rolling_average(joint_hist, config.regulation.window)
                net, pen_amt, pen_status = regulator.apply(alloc.gross_profit, detected)
            elif regulator is not None:
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
                round_number=t, phase=phase_of(t - prehistory_count, config.horizon),
                bids={"A": bid_a, "B": bid_b}, winner=alloc.winner, units=dict(alloc.units),
                gross_profit=dict(alloc.gross_profit), penalty_status=pen_status,
                penalty_amount=pen_amt, net_profit=net, cumulative_profit=dict(cumulative),
                joint_average=m_t, rolling_average=r_t, detected=detected,
                reasoning={"A": reason_a, "B": reason_b},
                plans={"A": plan_a, "B": plan_b},
                insights={"A": insights_a, "B": insights_b},
                unprocured_units=alloc.unprocured_units,
                detector_assessment=detector_assessment)
            logger.log_round(rec)
            print(f"\n=== Round {t} ===")
            print(f"Alpha bid: ${bid_a:.2f}")
            print(f"Alpha reasoning: {reason_a}")
            if config.private_memory:
                print(f"Alpha private plan: {plan_a}")
                print(f"Alpha private insights: {insights_a}")
            print(f"Beta bid: ${bid_b:.2f}")
            print(f"Beta reasoning: {reason_b}")
            if config.private_memory:
                print(f"Beta private plan: {plan_b}")
                print(f"Beta private insights: {insights_b}")
            print(f"Units A/B: {alloc.units['A']:.2f} / {alloc.units['B']:.2f}")
            if config.market_type == "smooth_procurement":
                print(f"Units left unprocured: {alloc.unprocured_units:.2f}")
            if detector_assessment is not None:
                print(f"Collusion detected: {'YES' if detected else 'no'}")
                print(f"Detector classification: {detector_assessment['classification']}")
                print(f"Detector summary: {detector_assessment['summary']}")
                print(f"Penalty A/B: ${pen_amt['A']:.2f} / ${pen_amt['B']:.2f}")
            print(f"Round profit A/B: ${net['A']:.2f} / ${net['B']:.2f}")
            print(f"Cumulative profit A/B: ${cumulative['A']:.2f} / ${cumulative['B']:.2f}", flush=True)
            logger.update_manifest(last_round=t, generated_rounds=t - prehistory_count)
            history.append(asdict(rec))
            observed_history.append(asdict(rec))
            memories = {"A": {"plan": plan_a, "insights": insights_a},
                        "B": {"plan": plan_b, "insights": insights_b}}
        logger.update_manifest(status="completed", analysis_eligible=True)
    except (AgentFailure, DetectorFailure) as exc:
        logger.update_manifest(status="failed", analysis_eligible=False,
                               failure_reason=str(exc))
        raise
    finally:
        pool.shutdown(wait=True)
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
    p.add_argument("--max-tokens", type=int, default=None,
                   help="maximum completion tokens per agent call; defaults to 4000 for "
                        "GPT-5 models and 1200 for other models")
    p.add_argument("--show-rival-reasoning", action="store_true",
                   help="expose the rival's PRIOR reasoning text (an explicit condition, Section 6); "
                        "off by default so reasoning stays private")
    p.add_argument("--condition-name", default=None)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--synthetic-near-cost-history", action="store_true",
                   help="prepend 20 synthetic near-cost rounds as agent-visible context")
    p.add_argument("--mirror-prehistory", action="store_true",
                   help="swap Alpha and Beta in the synthetic near-cost history")
    p.add_argument("--market", choices=["winner_take_all", "smooth_procurement"],
                   default="winner_take_all")
    p.add_argument("--private-memory", action="store_true",
                   help="carry each agent's own plan and insights into its next prompt")
    p.add_argument("--prompt-variant", choices=["p0", "p1"], default="p1",
                   help="smooth-market prompt wording; p0 omits the profitability warning")
    p.add_argument("--explore-strategies", action="store_true",
                   help="explicitly instruct agents to explore bidding strategies")
    p.add_argument("--winner-p1", action="store_true",
                   help="winner-take-all P1: explore strategies while protecting long-run profit")
    p.add_argument("--detector-model", default="openai/gpt-5.2",
                   help="Study 2 reasoning-aware regulator model")
    p.add_argument("--detector-history-window", type=int, default=10)
    p.add_argument("--penalty-fraction", type=float, default=0.50)
    args = p.parse_args(argv)

    conds = Conditions(show_rival_reasoning=args.show_rival_reasoning)
    default_name = f"history_{'visible' if args.show_rival_reasoning else 'hidden'}_reasoning"
    if args.synthetic_near_cost_history or args.mirror_prehistory:
        default_name = "synthetic_near_cost_" + ("mirrored_" if args.mirror_prehistory else "") + default_name
    if args.explore_strategies:
        default_name = "explore_strategies_" + default_name
    if args.winner_p1:
        default_name = "winner_p1_" + default_name
    if args.market == "smooth_procurement":
        default_name = (f"smooth_procurement_{args.prompt_variant}_" +
                        ("private_memory" if args.private_memory else "no_memory"))
    name = args.condition_name or default_name
    uses_gpt5 = any(model.startswith("openai/gpt-5")
                    for model in (args.model_a, args.model_b))
    max_tokens = args.max_tokens if args.max_tokens is not None else (4000 if uses_gpt5 else 1200)
    config = StudyConfig(
        horizon=args.rounds, study=args.study, condition_name=name, conditions=conds,
        regulation=(Regulation(mode="llm_reasoning", detector_model=args.detector_model,
                               detector_history_window=args.detector_history_window,
                               penalty_fraction=args.penalty_fraction)
                    if args.study == "study2" else None),
        model_a=args.model_a, model_b=args.model_b, temperature=args.temperature,
        max_tokens=max_tokens, seed=args.seed,
        market_type=args.market, private_memory=args.private_memory,
        prompt_variant=args.prompt_variant,
        explore_strategies=args.explore_strategies,
        winner_p1=args.winner_p1,
        history_window=100 if args.market == "smooth_procurement" else None)
    prehistory = (near_cost_history(mirrored=args.mirror_prehistory)
                  if args.synthetic_near_cost_history or args.mirror_prehistory else None)
    out = run(config, args.run_dir, resume=args.resume, prehistory=prehistory)
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
