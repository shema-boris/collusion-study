from auction.environment import draw_costs, select_winner
from auction.payoff import profits
from core.state import AgentId


def test_costs_are_reproducible_and_condition_independent():
    # Same (seed, round) -> identical costs, regardless of anything else.
    c1 = draw_costs(seed=7, round_number=3)
    c2 = draw_costs(seed=7, round_number=3)
    assert c1 == c2
    # Different rounds differ; this is what makes conditions comparable at fixed seed.
    assert draw_costs(7, 3) != draw_costs(7, 4)
    for c in c1.values():
        assert 40.0 <= c <= 60.0


def test_lowest_bid_past_gate_wins():
    bids = {AgentId.A: 70.0, AgentId.B: 65.0}
    quality = {AgentId.A: 8.0, AgentId.B: 8.0}
    assert select_winner(0, 1, bids, quality, gate=6.0) == AgentId.B


def test_gate_can_override_a_lower_bid():
    # B is cheaper but fails the quality gate, so A wins despite bidding higher.
    bids = {AgentId.A: 80.0, AgentId.B: 50.0}
    quality = {AgentId.A: 9.0, AgentId.B: 4.0}
    assert select_winner(0, 1, bids, quality, gate=6.0) == AgentId.A


def test_no_winner_when_none_clear_gate():
    bids = {AgentId.A: 80.0, AgentId.B: 50.0}
    quality = {AgentId.A: 3.0, AgentId.B: 4.0}
    assert select_winner(0, 1, bids, quality, gate=6.0) is None


def test_tie_break_is_deterministic_in_seed_round():
    bids = {AgentId.A: 60.0, AgentId.B: 60.0}
    quality = {AgentId.A: 8.0, AgentId.B: 8.0}
    w1 = select_winner(42, 5, bids, quality, gate=6.0)
    w2 = select_winner(42, 5, bids, quality, gate=6.0)
    assert w1 == w2 and w1 in (AgentId.A, AgentId.B)


def test_profits_winner_takes_margin_loser_zero():
    bids = {AgentId.A: 90.0, AgentId.B: 88.0}
    costs = {AgentId.A: 50.0, AgentId.B: 52.0}
    p = profits(bids, costs, winner=AgentId.A)
    assert p[AgentId.A] == 40.0
    assert p[AgentId.B] == 0.0
