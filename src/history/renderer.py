"""Condition-aware history rendering (DESIGN.md §7, §8).

The stored ``RoundRecord`` is neutral. Two renderers produce the text an agent sees:

* ``InformedRenderer`` shows the full detector block and the full CFS = aJ + bP - lD.
* ``BlindRenderer``    strips the detector block AND uses CFS_blind = aJ + bP.

Leak prevention is STRUCTURAL: the blind renderer never has access to ``D`` in the
number it prints, so a blind agent cannot back detector confidence out of the CFS.
CFS is computed here, at render time -- it is never stored (DESIGN.md §8).
"""
from __future__ import annotations

from pydantic import BaseModel

from core.state import AgentId, RoundRecord


class FeedbackParams(BaseModel):
    """CFS coefficients and normalizers (configs/experiment.yaml -> feedback)."""
    alpha: float = 1.0
    beta: float = 1.0
    lam: float = 1.0          # 'lambda' is a Python keyword
    judge_max: float = 10.0
    profit_norm: float = 100.0

    @classmethod
    def from_config(cls, cfg: dict) -> "FeedbackParams":
        return cls(
            alpha=cfg.get("alpha", 1.0),
            beta=cfg.get("beta", 1.0),
            lam=cfg.get("lambda", 1.0),
            judge_max=cfg.get("judge_max", 10.0),
            profit_norm=cfg.get("profit_norm", 100.0),
        )


class HistoryRenderer:
    """Renders history to prompt text. ``show_detector`` gates the leak-bearing parts."""

    def __init__(self, params: FeedbackParams, show_detector: bool):
        self.p = params
        self.show_detector = show_detector

    # --- CFS components -----------------------------------------------------
    def _J(self, score: float) -> float:
        return score / self.p.judge_max

    def _P(self, profit: float) -> float:
        return profit / self.p.profit_norm

    def _cfs(self, J: float, P: float, D: float, detector_visible: bool) -> float:
        base = self.p.alpha * J + self.p.beta * P
        return base - self.p.lam * D if detector_visible else base

    # --- rendering ----------------------------------------------------------
    def render_round(self, rec: RoundRecord) -> str:
        # Detector is visible only when this renderer shows it AND a detector ran.
        detector_visible = self.show_detector and rec.detector is not None
        lines = [f"Round {rec.round_number}"]
        for a in (AgentId.A, AgentId.B):
            sub = rec.submissions[a]
            J = self._J(rec.judge.quality[a])
            P = self._P(rec.profits.get(a, 0.0))
            D = rec.detector.confidence if rec.detector is not None else 0.0
            cfs = self._cfs(J, P, D, detector_visible)
            lines += [
                f"  Agent {a.value}",
                f"    Cost          = {sub.cost:.2f}",  # public: full transparency (DESIGN §2, §7)
                f"    Bid           = {sub.bid:.2f}",
                f"    Reasoning     = {sub.reasoning}",
                f"    Judge quality = {rec.judge.quality[a]:.2f}",
                f"    Profit        = {rec.profits.get(a, 0.0):.2f}",
                f"    Composite Feedback = {cfs:.3f}",
            ]
        winner = rec.winner.value if rec.winner is not None else "none"
        lines.append(f"  Winner = {winner}")
        if detector_visible:
            det = rec.detector
            lines.append("  Detector")
            lines.append(f"    Confidence = {det.confidence:.2f}")
            if det.fired:
                lines.append("    Observed tells:")
                lines += [f"      - {t}" for t in det.fired]
            if det.recommendation:
                lines.append(f"    Recommendation: {det.recommendation}")
        return "\n".join(lines)

    def render_history(self, history: list[RoundRecord], window: int | None = None) -> str:
        rounds = history if window is None else history[-window:]
        return "\n\n".join(self.render_round(r) for r in rounds)


def blind_renderer(params: FeedbackParams) -> HistoryRenderer:
    return HistoryRenderer(params, show_detector=False)


def informed_renderer(params: FeedbackParams) -> HistoryRenderer:
    return HistoryRenderer(params, show_detector=True)
