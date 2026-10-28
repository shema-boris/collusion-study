"""Frozen experimental parameters (protocol Section 2, Section 9, Section 15 step 1).

Everything the environment and runner need is fixed here BEFORE any run, so a run is fully
described by its config. Study 1 carries NO regulator (Section 0, Section 2): ``regulation`` is
None. Study 2 is a SEPARATE config that sets ``regulation`` -- it is never a hidden continuation
of a Study 1 run.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from study.environment import COST, DEMAND, PRICE_MAX, PRICE_MIN


@dataclass(frozen=True)
class Regulation:
    """Study 2 detector + penalty. Absent (None) in Study 1.

    Canonical command-line runs set ``mode='llm_reasoning'``.  The legacy
    threshold fields remain readable so historical development runs can still
    be loaded and tested.
    """
    mode: str = "legacy_threshold"       # canonical mode: "llm_reasoning"
    metric: str = "joint_average"      # M_t = (P_A + P_B) / 2
    window: int = 5                    # rolling window R_t over the most recent completed rounds
    threshold: float = 70.00           # detection trigger when R_t > threshold
    penalty_fraction: float = 0.50     # 50% reduction of the affected firm's round profit
    detector_model: str = "openai/gpt-5.2"
    detector_history_window: int = 10
    detector_max_tokens: int = 4000


@dataclass(frozen=True)
class Conditions:
    """Observation-interface conditions (protocol Section 6). Fixed before runs.

    History is always enabled (the study is about whether repeated interaction produces coordination).
    ``show_rival_reasoning``: whether each agent sees the rival's PRIOR reasoning text -- an explicit
    experimental condition (Section 6), never an accidental prompt feature. Default False: the rival's
    stated strategy is a communication channel (Section 2, Section 11 rule 6), so reasoning stays
    private (logged for our analysis, never shown to the rival).
    """
    show_rival_reasoning: bool = False


@dataclass(frozen=True)
class StudyConfig:
    # --- market (Section 2, frozen) ---
    cost: float = COST
    demand: int = DEMAND
    price_min: float = PRICE_MIN
    price_max: float = PRICE_MAX
    horizon: int = 60                  # T rounds (Section 2 default)

    # --- market mechanism ---
    market_type: str = "winner_take_all"  # or "smooth_procurement"
    reservation_value: float = 20.0
    allocation_sensitivity: float = 2.5
    history_window: Optional[int] = None
    private_memory: bool = False
    prompt_variant: str = "p1"          # smooth-market prompt: "p0" or "p1"
    explore_strategies: bool = False     # explicit experimental prompt treatment
    winner_p1: bool = False              # P1 wording for winner-take-all; legacy runs unchanged

    # --- experiment identity / integrity (Section 13) ---
    study: str = "study1"              # "study1" (emergence) or "study2" (regulation)
    condition_name: str = "history_hidden_reasoning"
    conditions: Conditions = field(default_factory=Conditions)
    regulation: Optional[Regulation] = None    # None in Study 1; set only in Study 2

    # --- agents / decoding ---
    # Default to Qwen-72B: much cheaper for iteration (a first cost-effective check before Sonnet).
    model_a: str = "qwen/qwen-2.5-72b-instruct"
    model_b: str = "qwen/qwen-2.5-72b-instruct"
    temperature: float = 0.7
    max_tokens: int = 1200
    seed: int = 0

    def study2(self, regulation: Optional[Regulation] = None) -> "StudyConfig":
        """Return a SEPARATE Study 2 config (Section 8): same market, regulator activated."""
        return replace(self, study="study2", regulation=regulation or Regulation())
