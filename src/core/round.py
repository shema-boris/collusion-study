"""``run_round`` -- the explicit, framework-independent orchestrator (DESIGN.md, §orchestration).

One round is a linear pipeline:

    draw costs -> render history view -> Agent A, Agent B -> Judge
        -> select winner -> payoffs -> Detector -> append RoundRecord

The three LLM-backed steps are passed in as callables (dependency injection), so the
orchestrator is testable with deterministic stubs and stays independent of any agent
framework. Real agent/judge/detector nodes will implement the same protocols.
"""
from __future__ import annotations

from typing import Callable, Optional, Protocol

from auction.environment import draw_costs, select_winner
from auction.payoff import profits as compute_profits
from auction.payoff import shared_award_profits, shared_award_shares
from core.state import (
    AgentId, Condition, DetectorRegime, ExperimentState,
    JudgeResult, RoundRecord, Scenario, Submission, Visibility,
)
from history.renderer import (
    FeedbackParams, blind_renderer, informed_renderer,
)


# --- node protocols ---------------------------------------------------------
class AgentFn(Protocol):
    def __call__(self, *, agent_id: AgentId, cost: float, scenario: Optional[Scenario],
                 history_text: str, round_number: int) -> Submission: ...


class JudgeFn(Protocol):
    def __call__(self, *, submissions: dict[AgentId, Submission],
                 scenario: Optional[Scenario], gate: float, round_number: int) -> JudgeResult: ...


class DetectorFn(Protocol):
    def __call__(self, *, state: ExperimentState, record: RoundRecord): ...


# --- orchestrator -----------------------------------------------------------
def run_round(
    state: ExperimentState,
    *,
    agent_fn: AgentFn,
    judge_fn: JudgeFn,
    detector_fn: Optional[DetectorFn],
    gate: float,
    feedback_params: FeedbackParams,
    scenario_provider: Optional[Callable[[int], Scenario]] = None,
    history_window: Optional[int] = None,
    max_context_tokens: Optional[int] = None,
    winner_rule: str = "lowest_bid",
    quality_weight: float = 0.0,
    detector_fine: float = 0.0,
    cost_low: float = 40.0,
    cost_high: float = 60.0,
    common_cost: bool = False,
    market: str = "winner_take_all",
    shared_award_mu: float = 0.10,
) -> RoundRecord:
    """Run one auction round, append its record to ``state.history``, and return it."""
    cond: Condition = state.condition
    r = state.round_number + 1

    # 0. Contract brief for this round (deterministic: round N -> scenario N). Economics come
    #    from the scenario (committed bank); cost_low/cost_high are only a fallback when no
    #    scenario is supplied (e.g. stub tests).
    scenario = scenario_provider(r) if scenario_provider is not None else None
    lo = scenario.cost_low if scenario is not None else cost_low
    hi = scenario.cost_high if scenario is not None else cost_high

    # 1. Costs -- seeded by (seed, round) only, so identical across conditions. common_cost=True
    #    gives both agents the SAME cost (symmetric; removes the cost-asymmetry barrier, §coord).
    costs = draw_costs(state.seed, r, lo, hi, common=common_cost)

    # 2. History view -- rendered per condition (leak prevention, DESIGN.md §7).
    if cond.use_history and state.history:
        renderer = (informed_renderer(feedback_params)
                    if cond.visibility is Visibility.INFORMED
                    else blind_renderer(feedback_params))
        # Token-budget sliding window (fit the most recent rounds under the context budget);
        # falls back to a fixed round-count window when no token budget is set.
        if max_context_tokens:
            history_text = renderer.render_history_budget(
                state.history, max_context_tokens, max_rounds=history_window)
        else:
            history_text = renderer.render_history(state.history, window=history_window)
    else:
        history_text = ""

    # 3. Agents bid independently (never see each other's current bid).
    submissions = {
        a: agent_fn(agent_id=a, cost=costs[a], scenario=scenario,
                    history_text=history_text, round_number=r)
        for a in (AgentId.A, AgentId.B)
    }

    # 4. Judge scores reasoning quality (the eligibility gate).
    judge = judge_fn(submissions=submissions, scenario=scenario, gate=gate, round_number=r)

    # 5. Award. winner_take_all: one winner takes the whole contract. shared_award: both suppliers
    #    win a demand SHARE of a divisible contract (both profit each round), so cooperation is
    #    jointly beneficial -- the setting where tacit collusion can emerge.
    bids = {a: submissions[a].bid for a in submissions}
    reference = scenario.reference_value if scenario is not None else 100.0
    shares = None
    if market == "shared_award":
        shares = shared_award_shares(bids, reference, mu=shared_award_mu)
        winner = max(shares, key=shares.get)   # largest-share supplier, for logging/detector
    elif winner_rule == "value":
        winner = select_winner(state.seed, r, bids, judge.quality, gate,
                               quality_weight=quality_weight, reference=reference, costs=costs)
    else:
        winner = select_winner(state.seed, r, bids, judge.quality, gate, costs=costs)

    record = RoundRecord(
        round_number=r, condition_name=cond.name, scenario=scenario,
        costs=costs, submissions=submissions,
        judge=judge, winner=winner, profits={}, detector=None,
    )

    # 6. Detector runs BEFORE profit, so its suspicion can tax the margin (DESIGN §5, §8).
    if cond.detector_regime is not DetectorRegime.NONE and detector_fn is not None:
        record.detector = detector_fn(state=state, record=record)
    detector_D = record.detector.confidence if record.detector is not None else 0.0

    # 7. Realized profit, taxed by the detector for INFORMED agents (visible + consequential
    #    oversight); blind runs the detector as a silent observer -- no penalty (clean control).
    fine = detector_fine if cond.visibility is Visibility.INFORMED else 0.0
    if market == "shared_award":
        record.profits = shared_award_profits(bids, costs, shares,
                                              detector_confidence=detector_D, fine=fine)
    else:
        record.profits = compute_profits(bids, costs, winner,
                                         detector_confidence=detector_D, fine=fine)

    state.history.append(record)
    state.round_number = r
    return record
