from auction.equilibrium import (
    collusion_level, competitive_bid, competitive_profit,
)


def test_competitive_bid_endpoints_and_midpoint():
    # b(c) = (c + 60) / 2  (DESIGN.md §3)
    assert competitive_bid(40.0) == 50.0
    assert competitive_bid(60.0) == 60.0
    assert competitive_bid(50.0) == 55.0


def test_competitive_profit():
    assert competitive_profit(40.0) == 10.0
    assert competitive_profit(60.0) == 0.0


def test_collusion_level_is_bid_above_competitive():
    # A $92 winning bid from a cost-50 agent whose competitive bid is $55 => +37.
    assert collusion_level(92.0, 50.0) == 92.0 - 55.0
    # Bidding exactly competitively yields zero collusion signal.
    assert collusion_level(competitive_bid(48.0), 48.0) == 0.0
