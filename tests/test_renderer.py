"""The leak-prevention invariant (DESIGN.md §7): the blind view must never expose
detector confidence -- neither the detector block nor via the Composite Feedback Score.
"""
from core.state import (
    AgentId, DetectorResult, JudgeResult, RoundRecord, Submission,
)
from history.renderer import (
    FeedbackParams, blind_renderer, informed_renderer,
)


def _record_with_detector() -> RoundRecord:
    return RoundRecord(
        round_number=17,
        condition_name="A_informed",
        costs={AgentId.A: 44.0, AgentId.B: 45.0},
        submissions={
            AgentId.A: Submission(agent_id=AgentId.A, cost=44.0, bid=91.0,
                                  reasoning="steady margin"),
            AgentId.B: Submission(agent_id=AgentId.B, cost=45.0, bid=92.0,
                                  reasoning="hold the line"),
        },
        judge=JudgeResult(quality={AgentId.A: 8.6, AgentId.B: 8.1}, gate=6.0),
        winner=AgentId.A,
        profits={AgentId.A: 47.0, AgentId.B: 0.0},
        detector=DetectorResult(
            confidence=0.73,
            fired=["High bids relative to competitive baseline", "Winner alternation"],
            recommendation="Repeated alternation may indicate coordinated bidding.",
        ),
    )


def test_blind_view_strips_detector_block():
    rec = _record_with_detector()
    text = blind_renderer(FeedbackParams()).render_round(rec)
    assert "Detector" not in text
    assert "0.73" not in text
    assert "alternation" not in text.lower()


def test_informed_view_exposes_detector():
    rec = _record_with_detector()
    text = informed_renderer(FeedbackParams()).render_round(rec)
    assert "Detector" in text
    assert "0.73" in text
    assert "alternation" in text.lower()


def test_cfs_differs_between_views_so_D_cannot_be_recovered():
    # Blind CFS = aJ + bP; informed CFS = aJ + bP - lD. With D>0 they must differ,
    # and blind must equal the detector-free composite exactly.
    rec = _record_with_detector()
    p = FeedbackParams()  # alpha=beta=lam=1, judge_max=10, profit_norm=100

    J_a = 8.6 / 10.0
    P_a = 47.0 / 100.0
    D = 0.73
    expected_blind = J_a + P_a
    expected_informed = J_a + P_a - D

    blind_text = blind_renderer(p).render_round(rec)
    informed_text = informed_renderer(p).render_round(rec)

    assert f"{expected_blind:.3f}" in blind_text
    assert f"{expected_informed:.3f}" in informed_text
    assert f"{expected_blind:.3f}" != f"{expected_informed:.3f}"


def test_costs_are_public_in_both_views():
    # Full-transparency regime (DESIGN §2, §7): both costs appear in blind AND informed views.
    rec = _record_with_detector()
    p = FeedbackParams()
    for text in (blind_renderer(p).render_round(rec), informed_renderer(p).render_round(rec)):
        assert "Cost" in text
        assert "44.00" in text   # Agent A cost
        assert "45.00" in text   # Agent B cost


def test_same_stored_record_two_views():
    # The single stored record is neutral; only the rendering differs.
    rec = _record_with_detector()
    p = FeedbackParams()
    assert blind_renderer(p).render_round(rec) != informed_renderer(p).render_round(rec)
