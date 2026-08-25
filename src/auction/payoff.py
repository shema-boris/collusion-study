"""Payoff computation (DESIGN.md §2.2, §8).

Two market mechanisms:
  * winner_take_all (``profits``): the winner earns (bid - cost); the loser earns 0. To share the
    surplus, agents must ROTATE -- collusion is fragile and needs coordination.
  * shared_award (``shared_award_shares`` + ``shared_award_profits``): both suppliers win a demand
    SHARE of a divisible contract (lower bid -> larger share, a Calvano-style logit), and an
    outside option at the reference value caps how high they can price. Both profit EVERY round, so
    "both hold high prices" is jointly profitable -- the setting where tacit collusion can emerge
    (cf. Fish, Gonczarowski & Shorrer 2024; Calvano et al. 2020).

Realized profit is taxed by the detector for informed agents: profit * (1 - detector_fine * D).
"""
from __future__ import annotations

import math
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


def shared_award_shares(bids: dict[AgentId, float], reference: float,
                        *, mu: float = 0.10) -> dict[AgentId, float]:
    """Logit demand share of a divisible contract: a LOWER bid earns a LARGER share.

    An outside option at ``reference`` (the buyer's reserve) means the two shares sum to < 1 -- if
    both bid near or above the reference, the buyer procures less, which caps collusion. ``mu`` is
    the (Calvano) horizontal-differentiation / temperature, scaled by the reference so the demand
    elasticity is comparable across contracts of different size.
    """
    tau = mu * max(reference, 1e-6)
    u = {a: math.exp(-bids[a] / tau) for a in bids}
    denom = sum(u.values()) + math.exp(-reference / tau)   # + buyer's outside option
    return {a: u[a] / denom for a in bids}


def shared_award_profits(bids: dict[AgentId, float], costs: dict[AgentId, float],
                         shares: dict[AgentId, float],
                         detector_confidence: float = 0.0, fine: float = 0.0
                         ) -> dict[AgentId, float]:
    """Both suppliers profit: (bid - cost) * share, taxed by the detector for informed agents.

    A high bid earns a fat margin but a small share; a low bid earns a big share but a thin margin
    -- so the profit-maximizing price is interior, and both agents gain when both price high.
    """
    tax = max(0.0, 1.0 - fine * detector_confidence)
    return {a: (bids[a] - costs[a]) * shares[a] * tax for a in bids}
