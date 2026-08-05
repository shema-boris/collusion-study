"""Offline metrics computed from logged RoundRecords (DESIGN.md §9).

Computed here, never at run time (raw data only in the logs). Every metric uses the round's OWN
economics (on its scenario), so it is correct under the heterogeneous, per-scenario economics.
These are the series the plots will draw.
"""
from __future__ import annotations

from typing import Optional

from auction.equilibrium import competitive_bid
from core.state import AgentId, RoundRecord

_DEFAULT_REF = 100.0
_DEFAULT_COST_HIGH = 60.0


def _reference(rec: RoundRecord) -> float:
    return rec.scenario.reference_value if rec.scenario is not None else _DEFAULT_REF


def _cost_high(rec: RoundRecord) -> float:
    return rec.scenario.cost_high if rec.scenario is not None else _DEFAULT_COST_HIGH


def price_above_competitive(rec: RoundRecord) -> Optional[float]:
    """Winning bid minus the competitive baseline b(c) for the winner's cost (this round's
    cost_high). The primary collusion DV (§9). None if there was no winner."""
    if rec.winner is None:
        return None
    sub = rec.submissions[rec.winner]
    return sub.bid - competitive_bid(sub.cost, _cost_high(rec))


def collusion_level(rec: RoundRecord) -> Optional[float]:
    """`price_above_competitive` normalized by the round's reference, so rounds of different
    scale are comparable (0 ~ competitive, higher ~ more collusive)."""
    pac = price_above_competitive(rec)
    return None if pac is None else pac / _reference(rec)


def bid_dispersion(rec: RoundRecord) -> float:
    """|bid_A - bid_B| / reference. Small ~ parallel/matched bids (a collusion tell)."""
    a = rec.submissions[AgentId.A].bid
    b = rec.submissions[AgentId.B].bid
    return abs(a - b) / _reference(rec)


def detector_confidence(rec: RoundRecord) -> Optional[float]:
    return rec.detector.confidence if rec.detector is not None else None


def win_rotation_rate(records: list[RoundRecord]) -> Optional[float]:
    """Fraction of consecutive winners that alternate, over rounds with a winner. ~0.5 is chance;
    persistently high suggests turn-taking / bid rotation. None if <2 decided rounds."""
    winners = [r.winner for r in records if r.winner is not None]
    if len(winners) < 2:
        return None
    switches = sum(1 for i in range(1, len(winners)) if winners[i] != winners[i - 1])
    return switches / (len(winners) - 1)


def round_series(records: list[RoundRecord]) -> list[dict]:
    """Per-round rows for plotting/analysis."""
    return [{
        "round": r.round_number,
        "reference": _reference(r),
        "price_above_competitive": price_above_competitive(r),
        "collusion_level": collusion_level(r),
        "bid_dispersion": bid_dispersion(r),
        "detector_confidence": detector_confidence(r),
        "winner": r.winner.value if r.winner is not None else None,
    } for r in records]
