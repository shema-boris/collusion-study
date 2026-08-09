"""Judge node: one LLM call -> a JudgeResult (DESIGN.md §2.1). Plugs into run_round's JudgeFn."""
from __future__ import annotations

from typing import Callable, Optional

from core.state import AgentId, JudgeResult, LLMCall, Scenario, Submission
from judge.prompts import JudgeOutput, judge_system, judge_user
from llm.client import LLMClient
from llm.parse import complete_structured


class JudgeParseError(RuntimeError):
    """Raised when the judge's scores could not be parsed after retries."""


def make_judge(client: LLMClient, *, seed: Optional[int] = None,
               log: Optional[Callable[[LLMCall], None]] = None):
    system = judge_system()

    def judge_fn(*, submissions: dict[AgentId, Submission], scenario: Optional[Scenario],
                 gate: float, round_number: int) -> JudgeResult:
        user = judge_user(scenario=scenario, submissions=submissions)
        out, _calls, err = complete_structured(
            client, system=system, user=user, schema=JudgeOutput,
            round_number=round_number, role="judge", seed=seed, log=log)
        if out is None:
            raise JudgeParseError(f"judge round {round_number}: {err}")
        quality, feedback = {}, {}
        for a in (AgentId.A, AgentId.B):
            if a.value not in out.quality:
                raise JudgeParseError(f"judge round {round_number}: missing score for {a.value}")
            quality[a] = float(out.quality[a.value])
            feedback[a] = (out.feedback or {}).get(a.value, "")
        return JudgeResult(quality=quality, gate=gate, feedback=feedback)

    return judge_fn
