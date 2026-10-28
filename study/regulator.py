"""Penalty application for Study 2.

The canonical experiments use the reasoning-aware detector in ``detector.py``;
that component produces a Boolean decision and this module applies the frozen
profit penalty.  The earlier rolling-price threshold is retained only for
backward compatibility with development tests and historical runs.

For either detector mode, a detected round's own positive gross profit is
reduced by ``penalty_fraction``. Zero-profit firms are never pushed negative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from study.config import Regulation


def joint_average(bid_a: float, bid_b: float) -> float:
    """Mean bid, retained as an informational metric in all runs."""
    return (float(bid_a) + float(bid_b)) / 2.0


def rolling_average(joint_history: list[float], window: int) -> Optional[float]:
    """R_t over the most recent ``window`` completed rounds (or all if fewer exist)."""
    if not joint_history:
        return None
    recent = joint_history[-window:]
    return sum(recent) / len(recent)


@dataclass
class Regulator:
    reg: Regulation

    def detected(self, r_t: Optional[float]) -> bool:
        return r_t is not None and r_t > self.reg.threshold

    def apply(self, gross_profit: dict[str, float], detected: bool
              ) -> tuple[dict[str, float], dict[str, float], dict[str, bool]]:
        """Return (net_profit, penalty_amount, penalty_status) for a completed round.

        A detected round taxes each firm's POSITIVE profit by ``penalty_fraction``; a firm that
        earned nothing that round is unaffected. Not detected -> net == gross, no penalty.
        """
        net, amount, status = {}, {}, {}
        for a in ("A", "B"):
            g = gross_profit[a]
            if detected and g > 0:
                pen = g * self.reg.penalty_fraction
                net[a], amount[a], status[a] = g - pen, pen, True
            else:
                net[a], amount[a], status[a] = g, 0.0, False
        return net, amount, status
