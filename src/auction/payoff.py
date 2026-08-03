"""Payoff computation (DESIGN.md §2.2): winner earns bid - cost, loser earns 0."""
from __future__ import annotations

from typing import Optional

from core.state import AgentId


def profits(bids: dict[AgentId, float], costs: dict[AgentId, float],
            winner: Optional[AgentId]) -> dict[AgentId, float]:
    return {
        a: (bids[a] - costs[a] if a == winner else 0.0)
        for a in bids
    }
