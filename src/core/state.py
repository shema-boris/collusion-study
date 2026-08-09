"""Shared data models — the single stored representation of the experiment.

Design invariant (DESIGN.md §7, §8): a ``RoundRecord`` stores only the RAW
components (judge quality, profit, detector confidence). It NEVER stores a
Composite Feedback Score, because the full CFS embeds detector confidence ``D``
and would leak it into the blind condition. CFS is computed at *render* time.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


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


# Reference cells + informed detector conditions. Blind conditions were removed: the detector
# only affects behaviour through visibility + the profit penalty, both of which require the agent
# to be INFORMED, so a blind detector condition is behaviourally identical to C1.
CONDITIONS: dict[str, Condition] = {
    "R0": Condition(name="R0", detector_regime=DetectorRegime.NONE,
                    visibility=Visibility.BLIND, use_history=False),
    "C1": Condition(name="C1", detector_regime=DetectorRegime.NONE,
                    visibility=Visibility.BLIND, use_history=True),
    "S_informed": Condition(name="S_informed", detector_regime=DetectorRegime.STATIC,
                            visibility=Visibility.INFORMED),
    "A_informed": Condition(name="A_informed", detector_regime=DetectorRegime.ADAPTIVE,
                            visibility=Visibility.INFORMED),
}


class Submission(BaseModel):
    agent_id: AgentId
    cost: float
    bid: float
    reasoning: str


class JudgeResult(BaseModel):
    """Per-submission quality scores, the eligibility gate, and per-proposal feedback."""
    quality: dict[AgentId, float]
    gate: float
    feedback: dict[AgentId, str] = Field(default_factory=dict)  # judge's one-line note per proposal

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


class Scenario(BaseModel):
    """A procurement contract brief with its economics (DESIGN.md §2).

    Economics live HERE, in the committed scenario bank, so each round's regime is part of the
    fixed, versioned specification and is logged automatically in every RoundRecord. The brief
    TEXT stays price-neutral (``render()`` never prints a value); ``reference_value`` is the
    numeric anchor the agent is shown, and costs are drawn from [cost_low, cost_high].
    The generator gives each scenario a UNIQUE triple (reference decorrelated from domain/round).
    Constraint: cost_low < cost_high < reference_value.
    """
    id: str
    title: str
    category: str
    summary: str
    deliverables: list[str]
    requirements: list[str]
    constraints: list[str]
    timeline: str
    risk_factors: list[str]
    success_criteria: list[str]
    reference_value: float = 100.0
    cost_low: float = 40.0
    cost_high: float = 60.0

    @model_validator(mode="after")
    def _check_economics(self):
        if not (self.cost_low < self.cost_high < self.reference_value):
            raise ValueError(
                f"scenario {self.id}: require cost_low < cost_high < reference_value, got "
                f"{self.cost_low} < {self.cost_high} < {self.reference_value}")
        return self

    def render(self) -> str:
        """Price-neutral solicitation brief the agent/judge reads (no economics in the text)."""
        def bullets(items: list[str]) -> list[str]:
            return [f"  - {x}" for x in items]
        lines = [
            f"[{self.id}] {self.title}",
            f"Category: {self.category}",
            "",
            f"Summary: {self.summary}",
            "",
            "Deliverables:", *bullets(self.deliverables),
            "Requirements:", *bullets(self.requirements),
            "Constraints:", *bullets(self.constraints),
            f"Timeline: {self.timeline}",
            "Risk factors:", *bullets(self.risk_factors),
            "Success criteria:", *bullets(self.success_criteria),
        ]
        return "\n".join(lines)


class RoundRecord(BaseModel):
    """The complete stored record of one round. Rendered per-condition on read."""
    round_number: int
    condition_name: str
    scenario: Optional[Scenario] = None    # the round's procurement brief (wired with LLM nodes)
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


class LLMCall(BaseModel):
    """One raw LLM interaction, logged verbatim for reproducibility/debugging (DESIGN.md §12).

    ``request`` holds the exact prompt sent -- including the rendered history the agent saw --
    so any run is fully reconstructable from the logs alone. Each round is a SINGLE call per
    role (agent_A, agent_B, judge, detector); there is no agentic tool loop.
    """
    round_number: int
    role: str                                  # "agent_A" | "agent_B" | "judge" | "detector"
    model: str
    temperature: float
    request: dict                              # {"system": ..., "user": ...} or {"messages": [...]}
    raw_response: str
    parsed_ok: bool = True
    error: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    attempt: int = 1
