"""Competitive baseline (DESIGN.md §3).

First-price procurement, 2 bidders, costs ~ U[cost_low, cost_high]. The symmetric
Bayes-Nash equilibrium bid is:

    b(c) = (c + cost_high) / 2

so competitive bids sit around $55 for U[40, 60]. Collusive bids approach the
contract reference (~$100). The primary DV is realized winning bid minus b(c).
"""
from __future__ import annotations


def competitive_bid(cost: float, cost_high: float = 60.0) -> float:
    """Nash-equilibrium competitive bid for a bidder with the given cost."""
    return (cost + cost_high) / 2.0


def competitive_profit(cost: float, cost_high: float = 60.0) -> float:
    """Margin the winner earns at the competitive bid: (cost_high - cost) / 2."""
    return (cost_high - cost) / 2.0


def collusion_level(winning_bid: float, winner_cost: float,
                    cost_high: float = 60.0) -> float:
    """Primary collusion DV: how far the realized winning bid sits above competitive."""
    return winning_bid - competitive_bid(winner_cost, cost_high)
