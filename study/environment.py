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
import math
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
    units: dict[str, float]               # units allocated to each firm
    gross_profit: dict[str, float]        # units * (bid - cost), before any Study 2 penalty
    unprocured_units: float = 0.0


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


def allocate_smooth(bid_a: float, bid_b: float, *, cost: float = COST,
                    demand: int = DEMAND, reservation_value: float = 20.0,
                    sensitivity: float = 2.5) -> Allocation:
    """Smooth divisible procurement with a buyer outside option.

    Each potential unit is allocated according to a multinomial-logit rule. Lower bids receive
    more units, while a higher bidder can retain a positive allocation. The outside option has
    weight one and represents demand left unprocured when bids are unattractive.
    """
    if sensitivity <= 0:
        raise ValueError("allocation sensitivity must be positive")
    bids = {"A": float(bid_a), "B": float(bid_b)}
    weights = {a: math.exp((reservation_value - bids[a]) / sensitivity) for a in AGENTS}
    denominator = 1.0 + weights["A"] + weights["B"]
    units = {a: demand * weights[a] / denominator for a in AGENTS}
    unprocured = demand / denominator
    gross = {a: units[a] * (bids[a] - cost) for a in AGENTS}
    winner = "A" if units["A"] > units["B"] else ("B" if units["B"] > units["A"] else None)
    return Allocation(winner=winner, units=units, gross_profit=gross,
                      unprocured_units=unprocured)


def competitive_benchmark(cost: float = COST) -> float:
    """The competitive (marginal-cost) price reference for the 'distance from benchmark' metric
    (Section 7). In a homogeneous Bertrand auction the competitive price is marginal cost."""
    return cost


def smooth_symmetric_benchmarks(*, cost: float = COST, price_max: float = PRICE_MAX,
                                reservation_value: float = 20.0,
                                sensitivity: float = 2.5,
                                demand: int = DEMAND) -> dict[str, float]:
    """Symmetric one-shot Nash and joint-profit prices for smooth procurement."""
    def shares(price: float) -> tuple[float, float]:
        weight = math.exp((reservation_value - price) / sensitivity)
        denominator = 1.0 + 2.0 * weight
        return weight / denominator, 1.0 / denominator

    def root(derivative) -> float:
        lo, hi = cost, price_max
        for _ in range(100):
            mid = (lo + hi) / 2.0
            if derivative(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    nash = root(lambda p: 1.0 - (p - cost) * (1.0 - shares(p)[0]) / sensitivity)
    joint = root(lambda p: 1.0 - (p - cost) * shares(p)[1] / sensitivity)
    nash_share, _ = shares(nash)
    joint_share, _ = shares(joint)
    return {
        "nash_price": nash,
        "joint_profit_price": joint,
        "nash_profit_per_firm": (nash - cost) * demand * nash_share,
        "joint_profit_per_firm": (joint - cost) * demand * joint_share,
    }
