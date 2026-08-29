"""Regulatory detector + penalty (protocol Section 8, Section 9) -- STUDY 2 ONLY.

Study 1 never imports this into its logic: the runner constructs a Regulator only when
``config.regulation`` is set (Study 2). Keeping it here honours the Section 12 requirement that
Study 1 be runnable without activating the regulatory component.

Frozen Section 9 mechanism:
    metric      M_t = (P_A + P_B) / 2
    rolling     R_t = mean of M over the most recent ``window`` COMPLETED rounds
                (or all available if fewer than ``window`` exist)
    threshold   detected when R_t > threshold
    penalty     detected rounds: each firm's positive round profit is reduced by penalty_fraction

Timing convention (frozen for Study 2, to be confirmed before Study 2 runs): the rolling average
is computed INCLUDING the just-completed round, and a detected round's own profit is penalised.
This must not change silently mid-project (Section 14).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from study.config import Regulation


def joint_average(bid_a: float, bid_b: float) -> float:
    """Detection metric M_t (Section 9)."""
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
