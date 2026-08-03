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
from core.state import CONDITIONS, Condition, DetectorRegime, ExperimentState
from detector.detector import make_detector
from history.renderer import FeedbackParams
from history.storage import RunLogger
from judge.judge import make_judge

ROOT = Path(__file__).resolve().parents[2]


def build_nodes(clients: dict, config: dict, condition: Condition, logger: RunLogger):
    reference = config["auction"]["contract_reference"]
    agent = make_bidding_agent(clients["agent"], reference_value=reference,
                               log=logger.log_llm_call)
    judge = make_judge(clients["judge"], log=logger.log_llm_call)
    detector = None
    if condition.detector_regime is not DetectorRegime.NONE:
        detector = make_detector(clients["detector"], log=logger.log_llm_call)
    return agent, judge, detector


def run(*, condition: Condition, seed: int, rounds: int, clients: dict, config: dict,
        runs_root, experiment: str = "exp", resume: bool = False,
        scenario_repo: Optional[ScenarioRepository] = None):
    """Run one (condition, seed) for `rounds` rounds. Returns the run directory."""
    repo = scenario_repo or ScenarioRepository.load(ROOT / "configs" / "scenarios.yaml")
    fb = FeedbackParams.from_config(config["feedback"])
    a = config["auction"]
    gate, cost_low, cost_high = a["quality_gate"], a["cost_low"], a["cost_high"]
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

    agent, judge, detector = build_nodes(clients, config, condition, logger)
    try:
        while state.round_number < rounds:
            rec = run_round(state, agent_fn=agent, judge_fn=judge, detector_fn=detector,
                            gate=gate, feedback_params=fb, scenario_provider=repo.get,
                            cost_low=cost_low, cost_high=cost_high)
            logger.log_round(rec)
            logger.log_event("info", "round", round=rec.round_number,
                             winner=rec.winner.value if rec.winner else None)
        logger.finalize("completed")
    except Exception as e:  # noqa: BLE001 - log, mark failed, and re-raise for the caller
        logger.log_event("error", "run aborted", error=str(e), at_round=state.round_number + 1)
        logger.finalize("failed")
        raise
    return logger.run_dir


def main(argv=None) -> None:
    from llm.client import clients_from_config
    from utils.config import load_yaml

    p = argparse.ArgumentParser(description="Run one condition x seed of the collusion study.")
    p.add_argument("--condition", required=True, choices=list(CONDITIONS))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--runs-root", default=str(ROOT / "runs" / "exp"))
    p.add_argument("--experiment", default="exp")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)

    config = load_yaml(ROOT / "configs" / "experiment.yaml")
    models_cfg = load_yaml(ROOT / "configs" / "models.yaml")
    config["_models_summary"] = {role: models_cfg[role]["model"] for role in models_cfg}
    clients = clients_from_config(models_cfg)

    run_dir = run(condition=CONDITIONS[args.condition], seed=args.seed, rounds=args.rounds,
                  clients=clients, config=config, runs_root=args.runs_root,
                  experiment=args.experiment, resume=args.resume)
    print(f"done -> {run_dir}")


if __name__ == "__main__":
    sys.exit(main())
