"""Shared data models — the single stored representation of the experiment.

Design invariant (DESIGN.md §7, §8): a ``RoundRecord`` stores only the RAW
components (judge quality, profit, detector confidence). It NEVER stores a
Composite Feedback Score, because the full CFS embeds detector confidence ``D``
and would leak it into the blind condition. CFS is computed at *render* time.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentId(str, Enum):
    A = "A"
    B = "B"

    @property
    def other(self) -> "AgentId":
        return AgentId.B if self is AgentId.A else AgentId.A


class DetectorRegime(str, Enum):
    NONE = "none"        # no detector node runs
    STATIC = "static"    # repository frozen after calibration
    ADAPTIVE = "adaptive"  # repository revised on the K-round clock


class Visibility(str, Enum):
    BLIND = "blind"        # detector signals stripped from the agents' history view
    INFORMED = "informed"  # agents see the full detector output


class Condition(BaseModel):
    """A run-level treatment cell (DESIGN.md §6)."""
    name: str
    detector_regime: DetectorRegime
    visibility: Visibility = Visibility.BLIND
    use_history: bool = True  # False only for the one-shot R0 baseline


# The 2x2 + two reference cells.
CONDITIONS: dict[str, Condition] = {
    "R0": Condition(name="R0", detector_regime=DetectorRegime.NONE,
                    visibility=Visibility.BLIND, use_history=False),
    "C1": Condition(name="C1", detector_regime=DetectorRegime.NONE,
                    visibility=Visibility.BLIND, use_history=True),
    "S_blind": Condition(name="S_blind", detector_regime=DetectorRegime.STATIC,
                         visibility=Visibility.BLIND),
    "S_informed": Condition(name="S_informed", detector_regime=DetectorRegime.STATIC,
                            visibility=Visibility.INFORMED),
    "A_blind": Condition(name="A_blind", detector_regime=DetectorRegime.ADAPTIVE,
                         visibility=Visibility.BLIND),
    "A_informed": Condition(name="A_informed", detector_regime=DetectorRegime.ADAPTIVE,
                            visibility=Visibility.INFORMED),
}


class Submission(BaseModel):
    agent_id: AgentId
    cost: float
    bid: float
    reasoning: str


class JudgeResult(BaseModel):
    """Per-submission reasoning-quality scores and the eligibility gate."""
    quality: dict[AgentId, float]
    gate: float

    def passed(self, agent: AgentId) -> bool:
        return self.quality[agent] >= self.gate

    def passers(self) -> list[AgentId]:
        return [a for a in self.quality if self.quality[a] >= self.gate]


class Indicator(BaseModel):
    """One learned coordination tell in the detector's repository (DESIGN.md §5.2)."""
    description: str
    weight: float
    examples: list[int] = Field(default_factory=list)  # round numbers


class DetectorResult(BaseModel):
    """Structured detector output for one round (DESIGN.md §5.4)."""
    confidence: float                                   # D in [0, 1]
    reasoning: str = ""
    evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""
    fired: list[str] = Field(default_factory=list)      # indicator descriptions that fired


class RoundRecord(BaseModel):
    """The complete stored record of one round. Rendered per-condition on read."""
    round_number: int
    condition_name: str
    costs: dict[AgentId, float]
    submissions: dict[AgentId, Submission]
    judge: JudgeResult
    winner: Optional[AgentId] = None
    profits: dict[AgentId, float] = Field(default_factory=dict)
    detector: Optional[DetectorResult] = None  # None when regime == NONE


class ExperimentState(BaseModel):
    """The only persistent state across rounds is the history (DESIGN.md §1, §7)."""
    condition: Condition
    seed: int
    round_number: int = 0
    history: list[RoundRecord] = Field(default_factory=list)
