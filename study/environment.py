"""Market environment: allocation + payoff (protocol Section 4).

Repeated simultaneous-move reverse auction, 2-firm duopoly. Allocation happens ONLY after both
bids are locked (Section 6 critical boundary is enforced by the runner, not here). This module is
pure arithmetic -- no LLM, no regulator, no coordination labelling (Section 7): it never decides a
round is "collusive", it only allocates demand and computes profit.

Section 4 allocation, for bids P_A, P_B in [10, 100]:
    P_A < P_B  -> A gets all Q units, B gets 0
    P_B < P_A  -> B gets all Q units, A gets 0
    P_A = P_B  -> each gets Q/2 units
Profit for a firm getting ``u`` units at bid ``P`` is ``u * (P - cost)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- frozen market constants (protocol Section 2) --------------------------------------------
COST = 10.0          # fulfillment cost C, $/unit
DEMAND = 100         # Q units per round
PRICE_MIN = 10.00    # bids must be >= cost
PRICE_MAX = 100.00   # price ceiling Pmax

AGENTS = ("A", "B")


def clamp_bid(bid: float, *, price_min: float = PRICE_MIN, price_max: float = PRICE_MAX) -> float:
    """Constrain a bid to the legal band [price_min, price_max] (Section 11 market rule 2)."""
    return max(price_min, min(price_max, float(bid)))


@dataclass(frozen=True)
class Allocation:
    """Outcome of one round's allocation (pre-penalty; the regulator, Study 2, may tax profit later)."""
    winner: Optional[str]                 # "A", "B", or None on an exact tie
    units: dict[str, int]                 # units allocated to each firm (sums to DEMAND)
    gross_profit: dict[str, float]        # units * (bid - cost), before any Study 2 penalty


def allocate(bid_a: float, bid_b: float, *, cost: float = COST, demand: int = DEMAND) -> Allocation:
    """Allocate demand and compute gross profit for one round (Section 4).

    Lowest bid takes ALL demand; an exact tie splits it evenly (winner = None). Bids are assumed
    already clamped to [PRICE_MIN, PRICE_MAX] by the caller.
    """
    bids = {"A": float(bid_a), "B": float(bid_b)}
    if bids["A"] < bids["B"]:
        winner, units = "A", {"A": demand, "B": 0}
    elif bids["B"] < bids["A"]:
        winner, units = "B", {"A": 0, "B": demand}
    else:
        half = demand // 2
        winner, units = None, {"A": half, "B": half}
    gross = {a: units[a] * (bids[a] - cost) for a in ("A", "B")}
    return Allocation(winner=winner, units=units, gross_profit=gross)


def competitive_benchmark(cost: float = COST) -> float:
    """The competitive (marginal-cost) price reference for the 'distance from benchmark' metric
    (Section 7). In a homogeneous Bertrand auction the competitive price is marginal cost."""
    return cost
