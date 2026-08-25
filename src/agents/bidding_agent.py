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
                       detector_fine: float = 0.0, adaptive: bool = False,
                       directive: bool = False, market: str = "winner_take_all",
                       prefix: Optional[str] = None, scaffold: bool = False):
    system = agent_system(detector_fine=detector_fine, adaptive=adaptive, directive=directive,
                          market=market, prefix=prefix, scaffold=scaffold)
    # Persistent 'plans & insights' strategy memory (Fish et al. 2024): this closure carries the
    # agent's own notes across rounds. Each make_bidding_agent instance is one agent (A or B), so
    # the state stays private to that agent.
    memory = {"plans": "", "insights": ""}

    def agent_fn(*, agent_id: AgentId, cost: float, scenario: Optional[Scenario],
                 history_text: str, round_number: int) -> Submission:
        reference_value = scenario.reference_value if scenario is not None else 100.0
        user = agent_user(scenario=scenario, cost=cost, reference_value=reference_value,
                          history_text=history_text, plans=memory["plans"],
                          insights=memory["insights"], scaffold=scaffold)
        out, _calls, err = complete_structured(
            client, system=system, user=user, schema=AgentOutput,
            round_number=round_number, role=f"agent_{agent_id.value}",
            seed=seed, log=log)
        if out is None:
            raise AgentParseError(f"agent_{agent_id.value} round {round_number}: {err}")
        if scaffold:  # carry the agent's updated strategy notes into its next round
            memory["plans"] = out.plans or memory["plans"]
            memory["insights"] = out.insights or memory["insights"]
        return Submission(agent_id=agent_id, cost=cost, bid=float(out.bid),
                          reasoning=out.reasoning, plans=out.plans, insights=out.insights)

    return agent_fn
