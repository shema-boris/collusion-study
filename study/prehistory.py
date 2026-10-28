"""Deterministic synthetic histories for boundary-condition experiments."""
from __future__ import annotations

from dataclasses import asdict

from study.environment import allocate
from study.runlog import RoundRecord


# Balanced analogue of the natural Kimi pattern: matching with occasional
# one-cent undercuts. Each firm wins twice and finishes with equal profit.
_NEAR_COST_BIDS = [
    (10.30, 10.30), (10.29, 10.29), (10.28, 10.28), (10.26, 10.27),
    (10.25, 10.25), (10.24, 10.24), (10.23, 10.23), (10.22, 10.22),
    (10.21, 10.20), (10.19, 10.19), (10.18, 10.18), (10.17, 10.17),
    (10.16, 10.16), (10.15, 10.14), (10.13, 10.13), (10.12, 10.12),
    (10.11, 10.11), (10.10, 10.10), (10.08, 10.09), (10.07, 10.07),
]


def near_cost_history(*, mirrored: bool = False) -> list[dict]:
    """Return 20 internally consistent synthetic completed rounds near cost."""
    cumulative = {"A": 0.0, "B": 0.0}
    result = []
    pairs = [(b, a) for a, b in _NEAR_COST_BIDS] if mirrored else _NEAR_COST_BIDS
    joint_history: list[float] = []
    for number, (bid_a, bid_b) in enumerate(pairs, start=1):
        outcome = allocate(bid_a, bid_b)
        for agent in ("A", "B"):
            cumulative[agent] = round(cumulative[agent] + outcome.gross_profit[agent], 2)
        joint = (bid_a + bid_b) / 2
        joint_history.append(joint)
        rolling = sum(joint_history[-5:]) / len(joint_history[-5:])
        record = asdict(RoundRecord(
            round_number=number, phase="synthetic_prehistory",
            bids={"A": bid_a, "B": bid_b}, winner=outcome.winner,
            units=dict(outcome.units), gross_profit=dict(outcome.gross_profit),
            penalty_status={"A": False, "B": False},
            penalty_amount={"A": 0.0, "B": 0.0},
            net_profit=dict(outcome.gross_profit), cumulative_profit=dict(cumulative),
            joint_average=joint, rolling_average=rolling, detected=False,
            reasoning={"A": "", "B": ""},
        ))
        record["synthetic"] = True
        result.append(record)
    return result
