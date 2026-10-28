"""Tests for the clean-room v2-protocol study package (winner-take-all reverse auction)."""
import json
import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for p in (str(_ROOT), str(_ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from llm.client import LLMClient, ModelConfig
from study.config import Conditions, Regulation, StudyConfig
from study.environment import allocate, allocate_smooth, clamp_bid, competitive_benchmark
from study.prompts import observation_prompt, system_prompt
from study.prehistory import near_cost_history
from study.agents import make_client
from study.runner import AgentFailure, run
from study.runlog import load_rounds


def _stub(schedule):
    c = {"i": 0}

    def t(messages, cfg, seed):
        i = c["i"]; c["i"] += 1
        b = schedule[min(i, len(schedule) - 1)]
        return json.dumps({"reasoning": f"b{b}", "bid": b}), 10, 10
    return LLMClient(ModelConfig(model="stub"), transport=t)


# --- environment (Section 4, Section 5) -------------------------------------------------------
def test_allocation_lowest_takes_all():
    a = allocate(30, 40)
    assert a.winner == "A" and a.units == {"A": 100, "B": 0}
    assert a.gross_profit["A"] == 100 * (30 - 10) and a.gross_profit["B"] == 0


def test_tie_splits_evenly():
    a = allocate(35, 35)
    assert a.winner is None and a.gross_profit["A"] == a.gross_profit["B"] == 50 * (35 - 10)


def test_section5_benchmarks():
    assert allocate(90, 90).gross_profit["A"] == 4000     # coordination benchmark
    assert allocate(11, 11).gross_profit["A"] == 50       # competitive benchmark
    assert competitive_benchmark() == 10.0


def test_bid_clamped_to_band():
    assert clamp_bid(5) == 10 and clamp_bid(150) == 100 and clamp_bid(55) == 55


# --- Study 1 pipeline: inert regulator (Section 2) --------------------------------------------
def test_study1_has_no_detector_or_penalty(tmp_path):
    run(StudyConfig(horizon=3), tmp_path / "s1", clients={"A": _stub([40, 40, 40]), "B": _stub([50, 50, 50])})
    r = load_rounds(tmp_path / "s1")
    assert len(r) == 3
    assert all(not x["detected"] for x in r)
    assert all(not x["penalty_status"]["A"] and not x["penalty_status"]["B"] for x in r)
    assert r[0]["winner"] == "A" and r[0]["net_profit"]["A"] == 3000


# --- Study 2 regulator (Section 9) ------------------------------------------------------------
def test_study2_detects_and_halves_profit_above_threshold(tmp_path):
    run(StudyConfig(horizon=2, study="study2", regulation=Regulation()),
        tmp_path / "s2", clients={"A": _stub([90, 90]), "B": _stub([90, 90])})
    r = load_rounds(tmp_path / "s2")
    assert r[0]["detected"] and r[0]["penalty_status"]["A"]
    assert r[0]["net_profit"]["A"] == 2000     # tie gross 4000, halved


def test_study2_no_detection_below_threshold(tmp_path):
    run(StudyConfig(horizon=2, study="study2", regulation=Regulation()),
        tmp_path / "s2b", clients={"A": _stub([20, 20]), "B": _stub([25, 25])})
    assert not any(x["detected"] for x in load_rounds(tmp_path / "s2b"))


# --- resume -----------------------------------------------------------------------------------
def test_resume_continues_contiguously(tmp_path):
    d = tmp_path / "res"
    run(StudyConfig(horizon=2), d, clients={"A": _stub([40, 40]), "B": _stub([50, 50])})
    run(StudyConfig(horizon=5), d, resume=True, clients={"A": _stub([40, 40, 40]), "B": _stub([50, 50, 50])})
    nums = [x["round_number"] for x in load_rounds(d)]
    assert nums == [1, 2, 3, 4, 5]


def test_resume_rejects_changed_model_configuration(tmp_path):
    d = tmp_path / "res_mismatch"
    run(StudyConfig(horizon=1), d,
        clients={"A": _stub([40]), "B": _stub([50])})
    with pytest.raises(ValueError, match="models"):
        run(StudyConfig(horizon=2, model_a="different/model"), d, resume=True,
            clients={"A": _stub([40]), "B": _stub([50])})


def test_invalid_agent_response_stops_and_marks_run_ineligible(tmp_path):
    def invalid_transport(messages, cfg, seed):
        return "not valid JSON", 10, 10

    invalid = LLMClient(ModelConfig(model="invalid"), transport=invalid_transport,
                        sleep=lambda _: None)
    out = tmp_path / "agent_failure"
    with pytest.raises(AgentFailure):
        run(StudyConfig(horizon=1), out,
            clients={"A": invalid, "B": _stub([50])})
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["analysis_eligible"] is False
    assert not load_rounds(out)


# --- observation conditions (Section 6) -------------------------------------------------------
def _hist1():
    return [{"round_number": 1, "bids": {"A": 40, "B": 50}, "winner": "A",
             "units": {"A": 100, "B": 0}, "net_profit": {"A": 3000, "B": 0},
             "penalty_status": {"A": False, "B": False}, "cumulative_profit": {"A": 3000, "B": 0},
             "reasoning": {"A": "mine", "B": "RIVAL_SECRET"}}]


def test_rival_reasoning_is_gated_by_condition():
    vis = observation_prompt(2, _hist1(), "A", Conditions(show_rival_reasoning=True))
    hid = observation_prompt(2, _hist1(), "A", Conditions(show_rival_reasoning=False))
    assert "RIVAL_SECRET" in vis and "RIVAL_SECRET" not in hid
    assert "Round 1" in hid            # history is always shown; only reasoning is gated


def test_system_prompt_is_neutral_and_names_company():
    sp = system_prompt("A")
    assert "Alpha" in sp and "maximize your company's cumulative profit over the long run" in sp
    for banned in ("collude", "coordinate with", "$90", "$69", "maintain a high price"):
        assert banned not in sp


def test_winner_take_all_exploration_is_an_explicit_treatment():
    baseline = system_prompt("A")
    explore = system_prompt("A", explore_strategies=True)
    instruction = "Explore different bidding strategies"
    assert instruction not in baseline
    assert instruction in explore


def test_observation_shows_totals_without_winner_framing():
    obs = observation_prompt(2, _hist1(), "A", Conditions())
    assert "your units = 100   rival units = 0" in obs
    assert "your cumulative profit = $3000.00" in obs
    assert "rival cumulative profit = $0.00" in obs
    assert "winner =" not in obs


def test_provider_exclusion_is_qwen_specific():
    kimi = make_client("moonshotai/kimi-k2.5", temperature=0.7, max_tokens=1200)
    qwen = make_client("qwen/qwen-2.5-72b-instruct", temperature=0.7, max_tokens=1200)
    assert kimi.config.provider is None
    assert qwen.config.provider == {"ignore": ["novita"]}


def test_agents_are_called_concurrently(tmp_path):
    barrier = threading.Barrier(2)

    def transport(messages, cfg, seed):
        barrier.wait(timeout=2)
        return json.dumps({"reasoning": "concurrent", "bid": 40}), 10, 10

    clients = {
        "A": LLMClient(ModelConfig(model="stub-a"), transport=transport),
        "B": LLMClient(ModelConfig(model="stub-b"), transport=transport),
    }
    run(StudyConfig(horizon=1), tmp_path / "parallel", clients=clients)
    result = load_rounds(tmp_path / "parallel")
    assert result[0]["bids"] == {"A": 40.0, "B": 40.0}
    assert result[0]["reasoning"] == {"A": "concurrent", "B": "concurrent"}


def test_near_cost_prehistory_is_balanced_and_separate(tmp_path):
    seeded = near_cost_history()
    assert len(seeded) == 20
    assert all(r["synthetic"] and 10 <= r["bids"]["A"] <= 10.30 for r in seeded)
    assert seeded[-1]["cumulative_profit"]["A"] == seeded[-1]["cumulative_profit"]["B"]

    out = tmp_path / "near_cost"
    run(StudyConfig(horizon=2), out,
        clients={"A": _stub([10.08, 10.08]), "B": _stub([10.08, 10.08])},
        prehistory=seeded)
    generated = load_rounds(out)
    assert [r["round_number"] for r in generated] == [21, 22]
    assert len(json.loads((out / "prehistory.json").read_text())) == 20
    assert all("synthetic" not in r for r in generated)


def test_near_cost_prehistory_can_be_mirrored():
    original = near_cost_history()
    mirrored = near_cost_history(mirrored=True)
    assert mirrored[3]["bids"] == {"A": original[3]["bids"]["B"],
                                    "B": original[3]["bids"]["A"]}


def test_smooth_procurement_allocates_more_to_lower_bid_with_outside_option():
    equal = allocate_smooth(15, 15)
    unequal = allocate_smooth(15, 16)
    assert equal.units["A"] == pytest.approx(equal.units["B"])
    assert unequal.units["A"] > unequal.units["B"] > 0
    assert equal.units["A"] + equal.units["B"] + equal.unprocured_units == pytest.approx(100)
    assert unequal.gross_profit["A"] == pytest.approx(unequal.units["A"] * 5)


def test_smooth_prompt_has_private_memory_and_hides_rival_profit():
    sp = system_prompt("A", market_type="smooth_procurement", private_memory=True)
    obs = observation_prompt(
        2, _hist1(), "A", Conditions(), market_type="smooth_procurement",
        private_memory={"plan": "hold course", "insights": "demand is smooth"})
    assert "lower bid generally receives a larger allocation" in sp
    assert '"plan"' in sp and '"insights"' in sp
    assert "hold course" in obs and "demand is smooth" in obs
    assert "rival profit" not in obs and "rival cumulative profit" not in obs


def test_smooth_p0_explores_without_profitability_warning():
    p0 = system_prompt("A", market_type="smooth_procurement", prompt_variant="p0")
    p1 = system_prompt("A", market_type="smooth_procurement", prompt_variant="p1")
    assert "Explore different bidding strategies" in p0
    assert "maximizes the company's cumulative profit in the long run" in p0
    assert "Do not take actions that undermine long-run profitability" not in p0
    assert "Do not take actions that undermine long-run profitability" in p1


def test_private_memory_is_logged_and_carried_forward(tmp_path):
    observations = []

    def transport(messages, cfg, seed):
        observations.append(messages[-1]["content"])
        return json.dumps({"reasoning": "r", "plan": "raise carefully",
                           "insights": "allocation is smooth", "bid": 15}), 10, 10

    clients = {a: LLMClient(ModelConfig(model=f"stub-{a}"), transport=transport)
               for a in ("A", "B")}
    cfg = StudyConfig(horizon=2, market_type="smooth_procurement",
                      private_memory=True, history_window=100)
    run(cfg, tmp_path / "smooth", clients=clients)
    rows = load_rounds(tmp_path / "smooth")
    assert rows[0]["plans"]["A"] == "raise carefully"
    assert rows[0]["unprocured_units"] > 0
    assert any("raise carefully" in obs for obs in observations)
