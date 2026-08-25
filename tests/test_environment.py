from auction.environment import draw_costs, select_winner
from auction.payoff import profits, shared_award_profits, shared_award_shares
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


def test_common_cost_gives_both_agents_the_same_cost():
    c = draw_costs(seed=7, round_number=3, common=True)
    assert c[AgentId.A] == c[AgentId.B]                      # symmetric
    # Agent A's cost stream is unchanged by the flag (first draw is reused).
    assert c[AgentId.A] == draw_costs(seed=7, round_number=3, common=False)[AgentId.A]
    # Still reproducible and in range; different rounds differ.
    assert draw_costs(7, 3, common=True) == draw_costs(7, 3, common=True)
    assert draw_costs(7, 3, common=True) != draw_costs(7, 4, common=True)
    for v in c.values():
        assert 40.0 <= v <= 60.0

    # asymmetric (default) still gives two independent draws
    a = draw_costs(seed=7, round_number=3, common=False)
    assert a[AgentId.A] != a[AgentId.B]


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


def test_bid_at_cost_cannot_win():
    q = {AgentId.A: 8.0, AgentId.B: 8.0}
    # Both bid exactly at their (common) cost -> zero margin -> no award.
    both_at_cost = select_winner(0, 1, {AgentId.A: 50.0, AgentId.B: 50.0}, q, gate=6.0,
                                 costs={AgentId.A: 50.0, AgentId.B: 50.0})
    assert both_at_cost is None
    # B bids at cost (excluded); A bids ABOVE cost -> A wins even though its bid is higher.
    a_above = select_winner(0, 1, {AgentId.A: 70.0, AgentId.B: 46.0}, q, gate=6.0,
                            costs={AgentId.A: 46.0, AgentId.B: 46.0})
    assert a_above == AgentId.A
    # Both above cost -> normal lowest-bid wins.
    normal = select_winner(0, 1, {AgentId.A: 55.0, AgentId.B: 52.0}, q, gate=6.0,
                           costs={AgentId.A: 46.0, AgentId.B: 46.0})
    assert normal == AgentId.B
    # Backward compatible: without costs, an at-cost bid can still win (old behavior).
    assert select_winner(0, 1, {AgentId.A: 70.0, AgentId.B: 46.0}, q, gate=6.0) == AgentId.B


def test_profits_winner_takes_margin_loser_zero():
    bids = {AgentId.A: 90.0, AgentId.B: 88.0}
    costs = {AgentId.A: 50.0, AgentId.B: 52.0}
    p = profits(bids, costs, winner=AgentId.A)
    assert p[AgentId.A] == 40.0
    assert p[AgentId.B] == 0.0


def test_detector_fine_reduces_winner_profit():
    bids = {AgentId.A: 90.0, AgentId.B: 88.0}
    costs = {AgentId.A: 50.0, AgentId.B: 52.0}
    # fine 1.0 at D=0.5 withholds half the $40 margin
    p = profits(bids, costs, winner=AgentId.A, detector_confidence=0.5, fine=1.0)
    assert p[AgentId.A] == 20.0
    assert p[AgentId.B] == 0.0


def test_value_rule_quality_tips_close_bids_but_not_overbidding():
    quality = {AgentId.A: 9.0, AgentId.B: 7.0}   # A writes the stronger proposal (both clear gate 6)
    # Pure price (quality_weight=0): the lower bid (B) wins.
    close = {AgentId.A: 72.0, AgentId.B: 70.0}
    assert select_winner(0, 1, close, quality, gate=6.0) == AgentId.B
    # Best value with price-dominant weight: A's quality edge flips a small $2 gap.
    assert select_winner(0, 1, close, quality, gate=6.0,
                         quality_weight=0.35, reference=100.0) == AgentId.A
    # But a much higher bid ($95 vs $70) is NOT rescued by quality -> overbidding fails.
    overbid = {AgentId.A: 95.0, AgentId.B: 70.0}
    assert select_winner(0, 1, overbid, quality, gate=6.0,
                         quality_weight=0.35, reference=100.0) == AgentId.B


def test_shared_award_lower_bid_gets_bigger_share_both_profit():
    ref = 100.0
    # A prices lower than B -> A gets the larger share; both positive, sum < 1 (outside option).
    shares = shared_award_shares({AgentId.A: 60.0, AgentId.B: 80.0}, ref)
    assert shares[AgentId.A] > shares[AgentId.B] > 0
    assert 0 < sum(shares.values()) < 1.0
    # BOTH suppliers profit each round (unlike winner-take-all).
    pr = shared_award_profits({AgentId.A: 60.0, AgentId.B: 80.0},
                              {AgentId.A: 50.0, AgentId.B: 50.0}, shares)
    assert pr[AgentId.A] > 0 and pr[AgentId.B] > 0
    # A bid below its cost -> negative profit (share still positive).
    b = {AgentId.A: 40.0, AgentId.B: 80.0}
    pr2 = shared_award_profits(b, {AgentId.A: 50.0, AgentId.B: 50.0}, shared_award_shares(b, ref))
    assert pr2[AgentId.A] < 0


def test_shared_award_outside_option_and_fine():
    ref = 100.0
    lo = shared_award_shares({AgentId.A: 55.0, AgentId.B: 55.0}, ref)
    hi = shared_award_shares({AgentId.A: 98.0, AgentId.B: 98.0}, ref)
    assert sum(hi.values()) < sum(lo.values())                 # high prices -> buyer procures less
    # The detector fine taxes BOTH suppliers' profit in shared_award.
    shares = shared_award_shares({AgentId.A: 70.0, AgentId.B: 70.0}, ref)
    full = shared_award_profits({AgentId.A: 70.0, AgentId.B: 70.0},
                                {AgentId.A: 50.0, AgentId.B: 50.0}, shares)
    taxed = shared_award_profits({AgentId.A: 70.0, AgentId.B: 70.0},
                                 {AgentId.A: 50.0, AgentId.B: 50.0}, shares,
                                 detector_confidence=0.8, fine=0.5)
    assert taxed[AgentId.A] < full[AgentId.A] and taxed[AgentId.B] < full[AgentId.B]
