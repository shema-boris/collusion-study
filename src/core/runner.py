"""Experiment runner: the outer loop over rounds for one condition x seed (DESIGN.md §10, §12).

Wires live clients -> nodes -> run_round -> RunLogger, with resume and fail-safe finalize.
`run()` takes an already-built clients dict so it is testable offline; `main()` builds live
OpenRouter clients from configs/models.yaml.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

ROUND_RETRIES = 5  # retry a whole round this many times before aborting the run (rides out flaky providers)

from agents.bidding_agent import make_bidding_agent
from auction.scenarios import ScenarioRepository
from core.round import run_round
from core.state import AgentId, CONDITIONS, Condition, DetectorRegime, ExperimentState, Scenario
from detector.detector import make_detector
from history.renderer import FeedbackParams
from history.storage import RunLogger
from judge.judge import make_judge

ROOT = Path(__file__).resolve().parents[2]


def build_nodes(clients: dict, condition: Condition, logger: RunLogger,
                detector_fine: float = 0.0, directive: bool = False,
                market: str = "winner_take_all", prefix=None, scaffold: bool = False):
    # The agent reads the reference from each round's scenario, so no reference is baked here.
    # Informed agents are TOLD the penalty rule (visible + consequential oversight); the clause
    # is only added when the fine is actually live, so blind/unpenalized runs get the plain prompt.
    from core.state import Visibility
    agent_fine = (detector_fine if condition.visibility is Visibility.INFORMED
                  and condition.detector_regime is not DetectorRegime.NONE else 0.0)
    adaptive = condition.detector_regime is DetectorRegime.ADAPTIVE
    agent_a = make_bidding_agent(clients["agent"], log=logger.log_llm_call, detector_fine=agent_fine,
                                 adaptive=adaptive, directive=directive, market=market,
                                 prefix=prefix, scaffold=scaffold)
    # Heterogeneous agents: B uses clients["agent_b"] if present (different model), else the same
    # model as A. Both share the identical prompt -- only the underlying model differs.
    b_client = clients.get("agent_b", clients["agent"])
    agent_b = make_bidding_agent(b_client, log=logger.log_llm_call, detector_fine=agent_fine,
                                 adaptive=adaptive, directive=directive, market=market,
                                 prefix=prefix, scaffold=scaffold)

    def agent(*, agent_id, **kw):  # route each slot to its own model
        return (agent_a if agent_id is AgentId.A else agent_b)(agent_id=agent_id, **kw)

    judge = make_judge(clients["judge"], log=logger.log_llm_call)
    detector = None
    if condition.detector_regime is not DetectorRegime.NONE:
        detector = make_detector(clients["detector"], log=logger.log_llm_call)
    return agent, judge, detector


def run(*, condition: Condition, seed: int, rounds: int, clients: dict, config: dict,
        runs_root, experiment: str = "exp", resume: bool = False,
        scenario_repo: Optional[ScenarioRepository] = None,
        reference: Optional[float] = None, cost_low: Optional[float] = None,
        cost_high: Optional[float] = None, window: Optional[int] = None,
        pin_scenario: Optional[int] = None):
    """Run one (condition, seed) for `rounds` rounds. Returns the run directory.

    Economics live on the scenarios (committed bank), so each round's regime is logged in its
    RoundRecord. The economics are NOT fixed (DESIGN.md §2, §3, §11): pass `reference`,
    `cost_low`, `cost_high` to REWRITE the scenarios' economics uniformly for this run (a
    convenient sweep knob); the override is recorded in the manifest. ``pin_scenario`` (a 1-based
    bank index) uses the SAME contract every round -- combined with the economics overrides this
    makes a fully STATIONARY market (byte-for-byte identical rounds, cf. Fish et al.).
    """
    repo = scenario_repo or ScenarioRepository.load(ROOT / "configs" / "scenarios.yaml")

    if pin_scenario is not None:
        pinned = repo.get(int(pin_scenario))          # same contract every round (stationary market)
        base_provider = lambda r: pinned              # noqa: E731
        config = {**config, "_pin_scenario": int(pin_scenario)}
    else:
        # Walk the bank in a seeded permutation so economics don't climb with the round index
        # (the bank is sorted). Order depends on seed only -> shared across conditions, varies by
        # seed. `scenario_order: sequential` in config restores the raw round-N -> scenario-N map.
        shuffle = config.get("scenario_order", "shuffled") != "sequential"
        base_provider = repo.ordered_provider(seed, shuffle=shuffle)

    overrides = {}
    if reference is not None:
        overrides["reference_value"] = reference
    if cost_low is not None:
        overrides["cost_low"] = cost_low
    if cost_high is not None:
        overrides["cost_high"] = cost_high
    if overrides:
        Scenario.model_validate({**base_provider(1).model_dump(), **overrides})  # fail fast on bad econ

        def scenario_provider(r):
            return Scenario.model_validate({**base_provider(r).model_dump(), **overrides})

        config = {**config, "_economics_override": overrides}
    else:
        scenario_provider = base_provider

    fb = FeedbackParams.from_config(config["feedback"])
    auction = config["auction"]
    gate = auction["quality_gate"]
    winner_rule = auction.get("winner_rule", "lowest_bid")
    quality_weight = auction.get("quality_weight", 0.0)
    detector_fine = auction.get("detector_fine", 0.0)
    common_cost = bool(auction.get("common_cost", False))
    directive = bool(auction.get("directive_prompt", False))  # labeled capability probe (not emergent)
    market = auction.get("market", "winner_take_all")          # or "shared_award" (divisible contract)
    shared_award_mu = float(auction.get("shared_award_mu", 0.10))
    prefix = auction.get("prefix")                             # None | p0 | p1 | p2 (Fish et al.)
    scaffold = bool(auction.get("scaffold", False))            # persistent plans & insights memory
    show_reasoning = not bool(auction.get("hide_reasoning", False))  # hide rival's reasoning text
    # Sliding window: agents see the most recent `history_window` rounds (DESIGN §10). Keeps the
    # prompt under the context limit on long runs. From --window, else config, else full history.
    hist_cfg = config.get("history") or {}
    history_window = window if window is not None else hist_cfg.get("max_window_rounds")
    max_context_tokens = hist_cfg.get("max_context_tokens")
    models = config.get("_models_summary")

    if resume:
        logger, prior = RunLogger.resume(runs_root, condition=condition, seed=seed,
                                         planned_rounds=rounds, config=config,
                                         models=models, experiment=experiment)
        state = ExperimentState(condition=condition, seed=seed,
                                round_number=(prior[-1].round_number if prior else 0),
                                history=prior)
    else:
        logger = RunLogger.create(runs_root, condition=condition, seed=seed,
                                  planned_rounds=rounds, config=config,
                                  models=models, experiment=experiment)
        state = ExperimentState(condition=condition, seed=seed)

    agent, judge, detector = build_nodes(clients, condition, logger, detector_fine, directive,
                                         market, prefix, scaffold)
    try:
        while state.round_number < rounds:
            next_round = state.round_number + 1
            for attempt in range(1, ROUND_RETRIES + 1):
                try:
                    rec = run_round(state, agent_fn=agent, judge_fn=judge, detector_fn=detector,
                                    gate=gate, feedback_params=fb, scenario_provider=scenario_provider,
                                    history_window=history_window, max_context_tokens=max_context_tokens,
                                    winner_rule=winner_rule, quality_weight=quality_weight,
                                    detector_fine=detector_fine, common_cost=common_cost,
                                    market=market, shared_award_mu=shared_award_mu,
                                    show_reasoning=show_reasoning)
                    break
                except Exception as e:  # transient node/provider failure -> retry the whole round
                    logger.log_event("warn", "round failed; retrying", round=next_round,
                                     attempt=attempt, error=str(e))
                    if attempt == ROUND_RETRIES:
                        raise
                    print(f"  {condition.name} r{next_round}: attempt {attempt} failed "
                          f"({e}); retrying...", flush=True)
                    time.sleep(min(30.0, 4.0 * (2 ** (attempt - 1))))  # 4,8,16,30s -- ride out overloads
            logger.log_round(rec)
            logger.log_event("info", "round", round=rec.round_number,
                             winner=rec.winner.value if rec.winner else None)
            sa, sb = rec.submissions[AgentId.A], rec.submissions[AgentId.B]
            print(f"  {condition.name} r{rec.round_number}/{rounds}: "
                  f"A ${sa.bid:.0f}/c{sa.cost:.0f}  B ${sb.bid:.0f}/c{sb.cost:.0f}  "
                  f"win={rec.winner.value if rec.winner else '-'}", flush=True)
        logger.finalize("completed")
    except Exception as e:  # noqa: BLE001 - log, mark failed, and re-raise for the caller
        logger.log_event("error", "run aborted", error=str(e), at_round=state.round_number + 1)
        logger.finalize("failed")
        raise
    return logger.run_dir


def load_live_context(agent_model: Optional[str] = None,
                      agent_max_tokens: Optional[int] = None,
                      agent_b_model: Optional[str] = None) -> tuple[dict, dict]:
    """Load .env + configs and build live OpenRouter clients. Shared by the CLI and batch runner.

    ``agent_model`` overrides the agent's model slug (for the model-swap experiment); it does NOT
    touch the judge or detector. ``agent_max_tokens`` raises the agent's reply budget -- reasoning
    models (QwQ, R1) emit a long chain-of-thought and truncate at the default 1024, so bump it
    (~4000-8000) when swapping one in. ``agent_b_model`` gives Agent B a DIFFERENT model from A
    (heterogeneous agents) -- the control that removes the same-model homogeneity confound; unset
    -> both agents share one model (current behavior). The dotenv import is soft so the package
    still works when python-dotenv isn't installed.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from llm.client import clients_from_config
    from utils.config import load_yaml

    config = load_yaml(ROOT / "configs" / "experiment.yaml")
    models_cfg = load_yaml(ROOT / "configs" / "models.yaml")
    if agent_model:
        models_cfg["agent"]["model"] = agent_model
    if agent_max_tokens:
        models_cfg["agent"]["max_tokens"] = agent_max_tokens
    if agent_b_model:  # heterogeneous: B copies A's config with a different model slug
        models_cfg["agent_b"] = {**models_cfg["agent"], "model": agent_b_model}
    config["_models_summary"] = {role: models_cfg[role]["model"] for role in models_cfg}
    return config, clients_from_config(models_cfg)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Run one condition x seed of the collusion study.")
    p.add_argument("--condition", required=True, choices=list(CONDITIONS))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--experiment", default="exp")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--window", type=int, default=None,
                   help="history window in rounds (default from config; keeps prompts under context)")
    p.add_argument("--reference", type=float, default=None,
                   help="override contract reference value (base from config); for sweeps")
    p.add_argument("--cost-low", type=float, default=None, help="override cost lower bound")
    p.add_argument("--cost-high", type=float, default=None, help="override cost upper bound")
    p.add_argument("--pin-scenario", type=int, default=None,
                   help="use the SAME contract (1-based bank index) every round -- with fixed "
                        "economics this makes a fully stationary market (identical rounds)")
    p.add_argument("--common-cost", action="store_true",
                   help="both agents get the SAME cost each round (symmetric; Bertrand benchmark)")
    p.add_argument("--quality-weight", type=float, default=None,
                   help="override auction.quality_weight (0 = pure lowest-bid; clean Bertrand test)")
    p.add_argument("--directive-prompt", action="store_true",
                   help="CAPABILITY PROBE (not emergent): instruct the agent to predict+undercut the "
                        "rival above cost. Prescribes competition -- do not read as spontaneous behavior.")
    p.add_argument("--agent-model", default=None,
                   help="override the AGENT model slug (model-swap experiment), e.g. qwen/qwq-32b")
    p.add_argument("--agent-max-tokens", type=int, default=None,
                   help="raise the agent reply budget (bump to ~4000-8000 for reasoning models)")
    p.add_argument("--agent-b-model", default=None,
                   help="give Agent B a DIFFERENT model (heterogeneous control), e.g. "
                        "--agent-model qwen/... --agent-b-model meta-llama/llama-3.3-70b-instruct")
    p.add_argument("--market", choices=["winner_take_all", "shared_award"], default=None,
                   help="market mechanism: winner_take_all (default) or shared_award (divisible "
                        "contract -- both suppliers profit by share; collusion can pay off jointly)")
    p.add_argument("--scaffold", action="store_true",
                   help="persistent plans & insights strategy memory carried across rounds (Fish et al.)")
    p.add_argument("--prefix", choices=["p0", "p1", "p2"], default=None,
                   help="Fish et al. prompt prefix: p0 neutral, p1 collusion-prone, p2 competition-leaning")
    p.add_argument("--hide-reasoning", action="store_true",
                   help="agents see only past bids + profits, NOT the rival's reasoning text "
                        "(proper tacit-collusion setting -- no communication channel)")
    args = p.parse_args(argv)

    config, clients = load_live_context(agent_model=args.agent_model,
                                        agent_max_tokens=args.agent_max_tokens,
                                        agent_b_model=args.agent_b_model)
    if (args.common_cost or args.quality_weight is not None or args.directive_prompt
            or args.market is not None or args.scaffold or args.prefix is not None
            or args.hide_reasoning):
        auction = {**config["auction"]}
        if args.common_cost:
            auction["common_cost"] = True
        if args.quality_weight is not None:
            auction["quality_weight"] = args.quality_weight
        if args.directive_prompt:
            auction["directive_prompt"] = True
        if args.market is not None:
            auction["market"] = args.market
        if args.scaffold:
            auction["scaffold"] = True
        if args.prefix is not None:
            auction["prefix"] = args.prefix
        if args.hide_reasoning:
            auction["hide_reasoning"] = True
        config = {**config, "auction": auction}
    run_dir = run(condition=CONDITIONS[args.condition], seed=args.seed, rounds=args.rounds,
                  clients=clients, config=config, runs_root=args.runs_root,
                  experiment=args.experiment, resume=args.resume, window=args.window,
                  reference=args.reference, cost_low=args.cost_low, cost_high=args.cost_high,
                  pin_scenario=args.pin_scenario)
    print(f"done -> {run_dir}")


if __name__ == "__main__":
    sys.exit(main())
