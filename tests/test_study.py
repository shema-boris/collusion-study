"""Tests for the clean-room v2-protocol study package (winner-take-all reverse auction)."""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for p in (str(_ROOT), str(_ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from llm.client import LLMClient, ModelConfig
from study.config import Conditions, Regulation, StudyConfig
from study.environment import allocate, clamp_bid, competitive_benchmark
from study.prompts import observation_prompt, system_prompt
from study.runner import run
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


# --- observation conditions (Section 6) -------------------------------------------------------
def _hist1():
    return [{"round_number": 1, "bids": {"A": 40, "B": 50}, "winner": "A",
             "units": {"A": 100, "B": 0}, "net_profit": {"A": 3000, "B": 0},
             "penalty_status": {"A": False, "B": False}, "cumulative_profit": {"A": 3000, "B": 0},
             "reasoning": {"A": "mine", "B": "RIVAL_SECRET"}}]


def test_rival_reasoning_is_gated_by_condition():
    vis = observation_prompt(2, _hist1(), "A", Conditions(history=True, show_rival_reasoning=True))
    hid = observation_prompt(2, _hist1(), "A", Conditions(history=True, show_rival_reasoning=False))
    assert "RIVAL_SECRET" in vis and "RIVAL_SECRET" not in hid


def test_no_history_control_hides_prior_rounds():
    noh = observation_prompt(2, _hist1(), "A", Conditions(history=False))
    assert "Round 1" not in noh and "3000" not in noh


def test_system_prompt_is_neutral_and_names_company():
    sp = system_prompt("A")
    assert "Alpha" in sp and "Maximize your cumulative net profit" in sp
    for banned in ("collude", "coordinate with", "$90", "$69", "maintain a high price"):
        assert banned not in sp
