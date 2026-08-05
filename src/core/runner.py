"""Experiment runner: the outer loop over rounds for one condition x seed (DESIGN.md §10, §12).

Wires live clients -> nodes -> run_round -> RunLogger, with resume and fail-safe finalize.
`run()` takes an already-built clients dict so it is testable offline; `main()` builds live
OpenRouter clients from configs/models.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from agents.bidding_agent import make_bidding_agent
from auction.scenarios import ScenarioRepository
from core.round import run_round
from core.state import AgentId, CONDITIONS, Condition, DetectorRegime, ExperimentState, Scenario
from detector.detector import make_detector
from history.renderer import FeedbackParams
from history.storage import RunLogger
from judge.judge import make_judge

ROOT = Path(__file__).resolve().parents[2]


def build_nodes(clients: dict, condition: Condition, logger: RunLogger):
    # The agent reads the reference from each round's scenario, so no reference is baked here.
    agent = make_bidding_agent(clients["agent"], log=logger.log_llm_call)
    judge = make_judge(clients["judge"], log=logger.log_llm_call)
    detector = None
    if condition.detector_regime is not DetectorRegime.NONE:
        detector = make_detector(clients["detector"], log=logger.log_llm_call)
    return agent, judge, detector


def run(*, condition: Condition, seed: int, rounds: int, clients: dict, config: dict,
        runs_root, experiment: str = "exp", resume: bool = False,
        scenario_repo: Optional[ScenarioRepository] = None,
        reference: Optional[float] = None, cost_low: Optional[float] = None,
        cost_high: Optional[float] = None, window: Optional[int] = None):
    """Run one (condition, seed) for `rounds` rounds. Returns the run directory.

    Economics live on the scenarios (committed bank), so each round's regime is logged in its
    RoundRecord. The economics are NOT fixed (DESIGN.md §2, §3, §11): pass `reference`,
    `cost_low`, `cost_high` to REWRITE the scenarios' economics uniformly for this run (a
    convenient sweep knob); the override is recorded in the manifest.
    """
    repo = scenario_repo or ScenarioRepository.load(ROOT / "configs" / "scenarios.yaml")

    overrides = {}
    if reference is not None:
        overrides["reference_value"] = reference
    if cost_low is not None:
        overrides["cost_low"] = cost_low
    if cost_high is not None:
        overrides["cost_high"] = cost_high
    if overrides:
        Scenario.model_validate({**repo.get(1).model_dump(), **overrides})  # fail fast on bad econ

        def scenario_provider(r):
            return Scenario.model_validate({**repo.get(r).model_dump(), **overrides})

        config = {**config, "_economics_override": overrides}
    else:
        scenario_provider = repo.get

    fb = FeedbackParams.from_config(config["feedback"])
    gate = config["auction"]["quality_gate"]
    # Sliding window: agents see the most recent `history_window` rounds (DESIGN §10). Keeps the
    # prompt under the context limit on long runs. From --window, else config, else full history.
    history_window = window if window is not None else (config.get("history") or {}).get("max_window_rounds")
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

    agent, judge, detector = build_nodes(clients, condition, logger)
    try:
        while state.round_number < rounds:
            rec = run_round(state, agent_fn=agent, judge_fn=judge, detector_fn=detector,
                            gate=gate, feedback_params=fb, scenario_provider=scenario_provider,
                            history_window=history_window)
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


def load_live_context() -> tuple[dict, dict]:
    """Load .env + configs and build live OpenRouter clients. Shared by the CLI and batch runner.

    The dotenv import is soft so the package still works when python-dotenv isn't installed.
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
    args = p.parse_args(argv)

    config, clients = load_live_context()
    run_dir = run(condition=CONDITIONS[args.condition], seed=args.seed, rounds=args.rounds,
                  clients=clients, config=config, runs_root=args.runs_root,
                  experiment=args.experiment, resume=args.resume, window=args.window,
                  reference=args.reference, cost_low=args.cost_low, cost_high=args.cost_high)
    print(f"done -> {run_dir}")


if __name__ == "__main__":
    sys.exit(main())
