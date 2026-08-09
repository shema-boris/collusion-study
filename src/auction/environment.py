"""Auction environment: cost generation and winner selection (DESIGN.md §2).

Reproducibility / experimental-control invariant (DESIGN.md §10, and the review):
cost draws and tie-breaks are seeded by (seed, round_number) ONLY -- never by
anything condition-specific. So seed ``s`` produces the identical cost sequence and
identical tie-breaks in every condition, and any behavioural difference between
conditions is attributable to the condition, not to different draws.

Cost and tie-break randomness use independent sub-streams so that adding/removing a
tie-break draw cannot shift the cost sequence.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.state import AgentId


def _substreams(seed: int, round_number: int) -> tuple[np.random.Generator, np.random.Generator]:
    """Two independent RNG streams for one round: (costs, tie-break)."""
    cost_ss, tie_ss = np.random.SeedSequence([int(seed), int(round_number)]).spawn(2)
    return np.random.default_rng(cost_ss), np.random.default_rng(tie_ss)


def draw_costs(seed: int, round_number: int,
               cost_low: float = 40.0, cost_high: float = 60.0) -> dict[AgentId, float]:
    """Private costs for both agents. Deterministic in (seed, round_number)."""
    cost_rng, _ = _substreams(seed, round_number)
    return {
        AgentId.A: float(cost_rng.uniform(cost_low, cost_high)),
        AgentId.B: float(cost_rng.uniform(cost_low, cost_high)),
    }


def select_winner(seed: int, round_number: int,
                  bids: dict[AgentId, float], quality: dict[AgentId, float],
                  gate: float, *, quality_weight: float = 0.0,
                  reference: float = 100.0) -> Optional[AgentId]:
    """Winner among submissions clearing the quality gate (DESIGN.md §2.1).

    Best-value (MEAT) score, higher wins:
        score = (1 - quality_weight) * (1 - bid/reference) + quality_weight * (quality/10)
    A lower bid and a higher quality both raise the score, with price weighted
    ``1 - quality_weight`` and quality ``quality_weight`` (so quality_weight < 0.5 keeps price
    dominant). ``quality_weight = 0`` reduces to pure lowest-bid. Returns None if neither clears
    the gate; ties are broken by the round's tie-break stream.
    """
    passers = [a for a in bids if quality[a] >= gate]
    if not passers:
        return None
    if quality_weight <= 0.0:
        score = {a: -bids[a] for a in passers}                    # lowest bid wins
    else:
        score = {a: (1 - quality_weight) * (1 - bids[a] / reference)
                    + quality_weight * (quality[a] / 10.0) for a in passers}
    best = max(score.values())
    leaders = [a for a in passers if score[a] == best]
    if len(leaders) == 1:
        return leaders[0]
    _, tie_rng = _substreams(seed, round_number)
    return leaders[int(tie_rng.integers(len(leaders)))]
