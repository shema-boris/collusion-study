"""Detector node: one LLM call -> a DetectorResult (DESIGN.md §5). Plugs into DetectorFn.

Sees the full record (bids + reasoning + costs, all public per §7), regardless of condition.
v1 single-call; see prompts.py for the planned §5.3 two-timescale upgrade.
"""
from __future__ import annotations

from typing import Callable, Optional

from core.state import AgentId, DetectorResult, ExperimentState, LLMCall, RoundRecord
from detector.prompts import DetectorOutput, detector_system, detector_user
from llm.client import LLMClient
from llm.parse import complete_structured


class DetectorParseError(RuntimeError):
    """Raised when the detector output could not be parsed after retries."""


def _round_summary(rec: RoundRecord) -> str:
    a, b = rec.submissions[AgentId.A], rec.submissions[AgentId.B]
    winner = rec.winner.value if rec.winner else "none"
    return (
        f"Round {rec.round_number}: A bid ${a.bid:.2f} (cost ${a.cost:.2f}); "
        f"B bid ${b.bid:.2f} (cost ${b.cost:.2f}); winner {winner}.\n"
        f"  A reasoning: {a.reasoning}\n  B reasoning: {b.reasoning}"
    )


def make_detector(client: LLMClient, *, window: int = 10, seed: Optional[int] = None,
                  log: Optional[Callable[[LLMCall], None]] = None):
    system = detector_system()

    def detector_fn(*, state: ExperimentState, record: RoundRecord) -> DetectorResult:
        recent = state.history[-window:]  # prior rounds (current not yet appended)
        recent_text = "\n".join(_round_summary(r) for r in recent) or "None yet."
        out, _calls, err = complete_structured(
            client, system=system,
            user=detector_user(recent_text=recent_text, current_text=_round_summary(record)),
            schema=DetectorOutput, round_number=record.round_number, role="detector",
            seed=seed, log=log)
        if out is None:
            raise DetectorParseError(f"detector round {record.round_number}: {err}")
        confidence = max(0.0, min(1.0, float(out.confidence)))
        return DetectorResult(confidence=confidence, reasoning=out.reasoning,
                              recommendation=out.recommendation, fired=out.tells)

    return detector_fn
