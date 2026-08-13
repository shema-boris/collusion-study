from pathlib import Path

import pytest

from auction.scenarios import ScenarioRepository

BANK = Path(__file__).resolve().parents[1] / "configs" / "scenarios.yaml"


@pytest.fixture(scope="module")
def repo() -> ScenarioRepository:
    return ScenarioRepository.load(BANK)   # parse the 3000-entry bank once for the module


def test_bank_loads_with_unique_ids(repo):
    assert len(repo) >= 5
    ids = [s.id for s in repo.all()]
    assert len(set(ids)) == len(ids)


def test_get_is_deterministic_index_by_round(repo):
    assert repo.get(1) is repo.all()[0]
    assert repo.get(len(repo)) is repo.all()[-1]
    # No randomness: the same round always yields the same scenario.
    assert repo.get(2).id == repo.get(2).id


def test_get_out_of_range_fails_fast(repo):
    with pytest.raises(IndexError):
        repo.get(len(repo) + 1)   # bank too small for this round
    with pytest.raises(IndexError):
        repo.get(0)               # rounds are 1-indexed


def test_render_is_price_neutral(repo):
    for s in repo.all():
        text = s.render()
        assert s.title in text
        assert "$" not in text                          # no price signaling


def test_every_scenario_has_required_content(repo):
    for s in repo.all():
        assert s.deliverables and s.requirements and s.constraints
        assert s.risk_factors and s.success_criteria


def test_full_bank_is_large_unique_and_covered(repo):
    assert len(repo) >= 3000
    scenarios = repo.all()
    # Contiguous 1-indexed ids: round N -> SCN-000N, one per round, no gaps.
    assert [s.id for s in scenarios] == [f"SCN-{i:04d}" for i in range(1, len(repo) + 1)]
    # Every rendered brief is distinct (uniqueness by construction).
    rendered = {s.render() for s in scenarios}
    assert len(rendered) == len(scenarios)


def test_seeded_order_is_reproducible_and_seed_dependent(repo):
    # Same seed -> identical permutation (reproducibility); different seed -> different walk.
    assert repo.order(0) == repo.order(0)
    assert repo.order(0) != repo.order(1)
    # A permutation: same multiset of indices, just reordered.
    assert sorted(repo.order(0)) == list(range(len(repo)))


def test_ordered_provider_walks_the_seeded_order(repo):
    order = repo.order(3)
    provider = repo.ordered_provider(3)
    assert provider(1) is repo.all()[order[0]]
    assert provider(5) is repo.all()[order[4]]
    with pytest.raises(IndexError):
        provider(0)
    with pytest.raises(IndexError):
        provider(len(repo) + 1)


def test_sequential_order_restores_raw_mapping(repo):
    provider = repo.ordered_provider(0, shuffle=False)
    assert provider(1) is repo.get(1)
    assert provider(7) is repo.get(7)


def test_shuffle_decorrelates_reference_from_round(repo):
    # The sorted bank climbs with the index; a seeded walk must break that monotonic ramp.
    refs = [repo.ordered_provider(0)(r).reference_value for r in range(1, 41)]
    ups = sum(b > a for a, b in zip(refs, refs[1:]))
    assert 0.25 * (len(refs) - 1) < ups < 0.75 * (len(refs) - 1)  # not monotonic either way


def test_duplicate_ids_rejected():
    from core.state import Scenario
    one = dict(id="X", title="t", category="c", summary="s",
               deliverables=["a"], requirements=["a"], constraints=["a"],
               timeline="t", risk_factors=["a"], success_criteria=["a"])
    with pytest.raises(ValueError):
        ScenarioRepository([Scenario(**one), Scenario(**one)])
