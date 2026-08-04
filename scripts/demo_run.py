"""Demo: run 3 rounds of condition C1 through the REAL agent/judge nodes, logging everything.

Uses fake transports (no network) that return well-formed JSON, so it exercises the full
node -> parse -> log path offline. Swap the transports for live OpenRouter calls by building
the clients from configs/models.yaml with an API key set. Then inspect with:

    python scripts/show_run.py runs/demo/C1__seed0

Usage:  python scripts/demo_run.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.bidding_agent import make_bidding_agent  # noqa: E402
from auction.scenarios import ScenarioRepository  # noqa: E402
from core.round import run_round  # noqa: E402
from core.state import CONDITIONS, ExperimentState  # noqa: E402
from history.renderer import FeedbackParams  # noqa: E402
from history.storage import RunLogger  # noqa: E402
from llm.client import LLMClient, ModelConfig  # noqa: E402

REPO = ScenarioRepository.load(ROOT / "configs" / "scenarios.yaml")
REFERENCE = 100.0


def _fake(transport_fn) -> LLMClient:
    return LLMClient(ModelConfig(model="fake"), transport=transport_fn, sleep=lambda _s: None)


def agent_transport(messages, cfg, seed):
    # Read the private cost from the prompt and bid cost + margin (lower cost -> lower bid).
    cost = float(re.search(r"production cost this round: \$([0-9.]+)", messages[1]["content"]).group(1))
    bid = round(cost + 15.0, 2)
    return (f'{{"bid": {bid}, "reasoning": "Priced to cover cost with a modest margin."}}', 380, 40)


def judge_transport(messages, cfg, seed):
    return ('{"quality": {"A": 8, "B": 8}, "notes": "Both proposals are adequate."}', 300, 25)


def main() -> None:
    cond = CONDITIONS["C1"]
    runs_root = ROOT / "runs" / "demo"
    state = ExperimentState(condition=cond, seed=0)

    with RunLogger.create(runs_root, condition=cond, seed=0, planned_rounds=3,
                          config={"gate": 6.0}, models={"agent": "fake-qwen", "judge": "fake-4o-mini"},
                          experiment="demo") as logger:
        agent = make_bidding_agent(_fake(agent_transport), log=logger.log_llm_call)
        judge = make_judge_client_node(logger)
        for _ in range(3):
            rec = run_round(state, agent_fn=agent, judge_fn=judge, detector_fn=None,
                            gate=6.0, feedback_params=FeedbackParams(),
                            scenario_provider=REPO.get)
            logger.log_round(rec)
            logger.log_event("info", "round complete", round=rec.round_number,
                             winner=rec.winner.value if rec.winner else None)

    print(f"wrote run to {(runs_root / 'C1__seed0').relative_to(ROOT)}")


def make_judge_client_node(logger):
    from judge.judge import make_judge
    return make_judge(_fake(judge_transport), log=logger.log_llm_call)


if __name__ == "__main__":
    main()
