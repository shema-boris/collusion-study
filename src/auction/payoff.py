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
                        *, mu: float = 0.10,
                        quality: Optional[dict[AgentId, float]] = None,
                        quality_weight: float = 0.0) -> dict[AgentId, float]:
    """Logit demand share of a divisible contract: a LOWER bid earns a LARGER share.

    The buyer's utility for supplier ``i`` reuses our best-value (MEAT) score verbatim:

        utility_i = (1 - w) * (1 - bid_i / reference) + w * (quality_i / 10)

    ``w`` = ``quality_weight`` is the SAME knob as the winner-take-all rule (environment.select_winner).
    It is Calvano's product-differentiation term ``a_i`` in disguise: with ``w = 0`` the market is
    homogeneous (pure price -> Bertrand race to cost); with ``w > 0`` a higher-quality supplier keeps
    demand at a HIGHER price, so an undercut no longer wipes it out -- the differentiation that gives
    tacit collusion room to hold (cf. Fish et al. 2024; Calvano et al. 2020).

    The outside option (buy nothing / reserve) is a supplier priced at the reference with zero quality,
    whose utility is 0. ``mu`` is the logit temperature. With ``w = 0`` this is algebraically identical
    to the previous pure-price share (softmax is shift-invariant), so existing runs are unchanged.
    """
    ref = max(reference, 1e-6)
    w = quality_weight
    q = quality or {}
    tau = max(mu, 1e-6)
    util = {a: (1 - w) * (1 - bids[a] / ref) + w * (q.get(a, 0.0) / 10.0) for a in bids}
    u = {a: math.exp(util[a] / tau) for a in bids}
    denom = sum(u.values()) + math.exp(0.0 / tau)   # + buyer's outside option (utility 0)
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
