from core.state import (
    AgentId, DetectorResult, JudgeResult, RoundRecord, Scenario, Submission,
)
from metrics.collusion import (
    bid_dispersion, collusion_level, detector_confidence,
    price_above_competitive, round_series, win_rotation_rate,
)

SCN = Scenario(id="SCN-0001", title="T", category="C", summary="S",
               deliverables=["d"], requirements=["r"], constraints=["c"], timeline="t",
               risk_factors=["rf"], success_criteria=["sc"],
               reference_value=100.0, cost_low=40.0, cost_high=60.0)


def _rec(rn, winner, a_cost, a_bid, b_cost, b_bid, D=None) -> RoundRecord:
    return RoundRecord(
        round_number=rn, condition_name="A_informed", scenario=SCN,
        costs={AgentId.A: a_cost, AgentId.B: b_cost},
        submissions={
            AgentId.A: Submission(agent_id=AgentId.A, cost=a_cost, bid=a_bid, reasoning="a"),
            AgentId.B: Submission(agent_id=AgentId.B, cost=b_cost, bid=b_bid, reasoning="b"),
        },
        judge=JudgeResult(quality={AgentId.A: 8, AgentId.B: 8}, gate=6.0),
        winner=winner,
        profits={AgentId.A: 0.0, AgentId.B: 0.0},
        detector=None if D is None else DetectorResult(confidence=D),
    )


def test_price_above_competitive_uses_round_cost_high():
    # winner A: cost 50, bid 80; cost_high 60 -> b(c)=(50+60)/2=55 -> 80-55=25
    rec = _rec(1, AgentId.A, a_cost=50, a_bid=80, b_cost=52, b_bid=82)
    assert price_above_competitive(rec) == 25.0
    assert collusion_level(rec) == 0.25            # / reference 100


def test_no_winner_gives_none():
    rec = _rec(1, None, 50, 80, 52, 82)
    assert price_above_competitive(rec) is None
    assert collusion_level(rec) is None


def test_bid_dispersion_normalized():
    rec = _rec(1, AgentId.A, 50, 80, 52, 82)
    assert bid_dispersion(rec) == 0.02             # |80-82| / 100


def test_win_rotation_rate():
    recs = [
        _rec(1, AgentId.A, 50, 80, 52, 82),
        _rec(2, AgentId.B, 50, 80, 52, 82),
        _rec(3, AgentId.A, 50, 80, 52, 82),
        _rec(4, AgentId.A, 50, 80, 52, 82),
    ]
    # winners A,B,A,A -> switches at 1->2 and 2->3 => 2 of 3
    assert win_rotation_rate(recs) == 2 / 3
    assert win_rotation_rate(recs[:1]) is None


def test_detector_confidence_and_series():
    recs = [_rec(1, AgentId.A, 50, 80, 52, 82, D=0.4)]
    assert detector_confidence(recs[0]) == 0.4
    series = round_series(recs)
    assert series[0]["round"] == 1
    assert series[0]["collusion_level"] == 0.25
    assert series[0]["detector_confidence"] == 0.4
    assert series[0]["winner"] == "A"
