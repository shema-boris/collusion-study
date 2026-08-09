"""Payoff computation (DESIGN.md §2.2, §8).

Realized winner profit = (bid - cost) * (1 - detector_fine * D); loser earns 0. The detection
fine defaults to 0 (off) so behaviour is unchanged until the detector is calibrated.
"""
from __future__ import annotations

from typing import Optional

from core.state import AgentId


def profits(bids: dict[AgentId, float], costs: dict[AgentId, float],
            winner: Optional[AgentId], detector_confidence: float = 0.0,
            fine: float = 0.0) -> dict[AgentId, float]:
    tax = max(0.0, 1.0 - fine * detector_confidence)   # suspicion withholds part of the margin
    return {
        a: ((bids[a] - costs[a]) * tax if a == winner else 0.0)
        for a in bids
    }
