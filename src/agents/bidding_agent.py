"""Bidding-agent node: one LLM call -> a Submission (DESIGN.md §2, §4).

Plugs into `run_round`'s AgentFn seam. Both Agent A and Agent B are built from the SAME
client (two independent instances of the same model). LLM calls are logged via the injected
`log` callback (into llm_calls.jsonl).
"""
from __future__ import annotations

from typing import Callable, Optional

from agents.prompts import AgentOutput, agent_system, agent_user
from core.state import AgentId, LLMCall, Scenario, Submission
from llm.client import LLMClient
from llm.parse import complete_structured


class AgentParseError(RuntimeError):
    """Raised when the model's bid could not be parsed after retries."""


def make_bidding_agent(client: LLMClient, *, seed: Optional[int] = None,
                       log: Optional[Callable[[LLMCall], None]] = None,
                       detector_fine: float = 0.0, adaptive: bool = False):
    system = agent_system(detector_fine=detector_fine, adaptive=adaptive)

    def agent_fn(*, agent_id: AgentId, cost: float, scenario: Optional[Scenario],
                 history_text: str, round_number: int) -> Submission:
        reference_value = scenario.reference_value if scenario is not None else 100.0
        user = agent_user(scenario=scenario, cost=cost,
                          reference_value=reference_value, history_text=history_text)
        out, _calls, err = complete_structured(
            client, system=system, user=user, schema=AgentOutput,
            round_number=round_number, role=f"agent_{agent_id.value}",
            seed=seed, log=log)
        if out is None:
            raise AgentParseError(f"agent_{agent_id.value} round {round_number}: {err}")
        return Submission(agent_id=agent_id, cost=cost, bid=float(out.bid),
                          reasoning=out.reasoning)

    return agent_fn
