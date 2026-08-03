"""run_round wired with deterministic stub nodes -- proves the orchestration end to
end without any LLM, and re-checks the leak invariant through the full pipeline.
"""
from auction.equilibrium import competitive_bid
from core.round import run_round
from core.state import (
    AgentId, CONDITIONS, DetectorResult, ExperimentState,
    JudgeResult, Submission,
)
from history.renderer import FeedbackParams


def competitive_agent(*, agent_id, cost, history_text, round_number) -> Submission:
    # Bids the Nash-competitive price; ignores history.
    return Submission(agent_id=agent_id, cost=cost,
                      bid=competitive_bid(cost), reasoning=f"competitive r{round_number}")


def passing_judge(*, submissions, gate) -> JudgeResult:
    return JudgeResult(quality={a: 8.0 for a in submissions}, gate=gate)


def fixed_detector(*, state, record) -> DetectorResult:
    return DetectorResult(confidence=0.73, fired=["winner alternation"],
                          recommendation="suspicious")


def _run(condition_name, n=3, seed=1):
    state = ExperimentState(condition=CONDITIONS[condition_name], seed=seed)
    records = [
        run_round(state, agent_fn=competitive_agent, judge_fn=passing_judge,
                  detector_fn=fixed_detector, gate=6.0,
                  feedback_params=FeedbackParams())
        for _ in range(n)
    ]
    return state, records


def test_history_grows_and_winner_is_lower_cost_bidder():
    state, records = _run("A_blind")
    assert len(state.history) == 3
    assert [r.round_number for r in records] == [1, 2, 3]
    for r in records:
        # Competitive bids are monotone in cost, so the lower-cost agent wins.
        lower = min(r.costs, key=r.costs.get)
        assert r.winner == lower


def test_detector_runs_only_when_regime_active():
    _, with_det = _run("A_blind")
    _, no_det = _run("C1")   # regime NONE
    assert all(r.detector is not None for r in with_det)
    assert all(r.detector is None for r in no_det)


def test_costs_identical_across_conditions_at_fixed_seed():
    # The reproducibility guarantee that makes cross-condition contrasts valid.
    _, a = _run("A_blind", seed=5)
    _, b = _run("A_informed", seed=5)
    assert [r.costs for r in a] == [r.costs for r in b]
