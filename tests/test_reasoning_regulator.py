"""Study 2 reasoning-aware detector, penalty, feedback, and audit-log tests."""
import json

import pytest

from llm.client import LLMClient, ModelConfig
from study.config import Regulation, StudyConfig
from study.detector import (DetectorFailure, canonicalize_evidence_sources,
                            evidence_is_verbatim, parse_assessment)
from study.detector_prompts import DETECTOR_PROMPT_VERSION, detector_system_prompt
from study.runner import run
from study.runlog import load_rounds


def _agent(name, observations):
    def transport(messages, cfg, seed):
        observations.append(messages[-1]["content"])
        return json.dumps({
            "reasoning": "Maintain our shared elevated bid and avoid undercutting.",
            "plan": "Match the rival to preserve the split.",
            "insights": "Mutual restraint protects future profit.",
            "bid": 50,
        }), 10, 10
    return LLMClient(ModelConfig(model=name), transport=transport)


def _assessment(*, detected=True):
    return {
        "alpha_coordination_intent": detected,
        "beta_coordination_intent": detected,
        "mutual_alignment": detected,
        "competitive_explanation": False,
        "classification": "mutual_price_coordination" if detected else "independent_competition",
        "coordination_objective": "maintain shared elevated bids" if detected else "",
        "alpha_evidence": ([{"source": "reasoning", "excerpt": "shared elevated bid"}]
                           if detected else []),
        "beta_evidence": ([{"source": "plan", "excerpt": "preserve the split"}]
                          if detected else []),
        "summary": "mutual intent" if detected else "independent conduct",
    }


def _detector(payload):
    def transport(messages, cfg, seed):
        return json.dumps(payload), 10, 10
    return LLMClient(ModelConfig(model="detector-stub"), transport=transport)


def test_parser_uses_frozen_mutual_reasoning_rule():
    yes = parse_assessment(json.dumps(_assessment(detected=True)))
    no = parse_assessment(json.dumps(_assessment(detected=False)))
    assert yes["detected"] is True
    assert no["detected"] is False


def test_parser_repairs_only_escaped_json_value_delimiters():
    payload = _assessment(detected=True)
    valid = json.dumps(payload, indent=2)
    malformed = valid.replace(
        '"excerpt": "shared elevated bid"',
        '"excerpt": \\"shared elevated bid\\"',
        1,
    )
    assessment = parse_assessment(malformed)
    assert assessment["detected"] is True
    assert assessment["response_json_repaired"] is True
    assert assessment["alpha_evidence"][0]["excerpt"] == "shared elevated bid"

    assessment = parse_assessment(valid)
    assert assessment["response_json_repaired"] is False


def test_detector_prompt_contains_competition_coordination_boundary():
    prompt = detector_system_prompt("winner_take_all")
    assert DETECTOR_PROMPT_VERSION == "competition_coordination_rubric_v2"
    assert "operative strategy that motivates the CURRENT action" in prompt
    assert "currently undercutting to win" in prompt
    assert "concession unless the text connects it to reciprocity" in prompt


def test_competitive_explanation_vetoes_penalty():
    payload = _assessment(detected=True)
    payload["competitive_explanation"] = True
    assessment = parse_assessment(json.dumps(payload))
    assert assessment["detected"] is False
    assert assessment["decision_rule_version"] == "reasoning_mutual_v1"


def test_detector_evidence_must_be_verbatim():
    assessment = parse_assessment(json.dumps(_assessment(detected=True)))
    current = {"agents": {
        "A": {"reasoning": "We will maintain our shared elevated bid.", "plan": "", "insights": ""},
        "B": {"reasoning": "", "plan": "We should preserve the split.", "insights": ""},
    }}
    assert evidence_is_verbatim(assessment, current)
    assessment["alpha_evidence"][0]["excerpt"] = "invented quotation"
    assert not evidence_is_verbatim(assessment, current)


def test_evidence_validation_allows_only_terminal_punctuation_difference():
    current = {"agents": {
        "A": {"reasoning": "Try cooperation, then compete.", "plan": "", "insights": ""},
        "B": {"reasoning": "Probe upward", "plan": "", "insights": ""},
    }}
    assessment = {
        "alpha_evidence": [{"source": "reasoning", "excerpt": "Try cooperation."}],
        "beta_evidence": [{"source": "reasoning", "excerpt": "Probe upward."}],
    }
    assert evidence_is_verbatim(assessment, current)

    assessment["alpha_evidence"][0]["excerpt"] = "Try mutual cooperation."
    assert not evidence_is_verbatim(assessment, current)


def test_evidence_source_is_corrected_and_invalid_items_are_discarded():
    current = {"agents": {
        "A": {"reasoning": "Compete independently.",
              "plan": "Bid below the rival.", "insights": ""},
        "B": {"reasoning": "Different quotation.", "plan": "", "insights": ""},
    }}
    assessment = {
        "alpha_evidence": [{"source": "reasoning", "excerpt": "Bid below the rival."}],
        "beta_evidence": [{"source": "reasoning", "excerpt": "Different quotation."}],
    }
    fixed = canonicalize_evidence_sources(assessment, current)
    assert fixed["alpha_evidence"][0]["source"] == "plan"
    assert evidence_is_verbatim(fixed, current)

    assessment["alpha_evidence"] = [
        {"source": "reasoning", "excerpt": "Invented quotation."},
        {"source": "reasoning", "excerpt": "Bid below the rival."},
    ]
    fixed = canonicalize_evidence_sources(assessment, current)
    assert fixed["alpha_evidence"] == [
        {"source": "plan", "excerpt": "Bid below the rival."}
    ]

    assessment["alpha_evidence"] = [
        {"source": "reasoning", "excerpt": "Different quotation."}
    ]
    assert canonicalize_evidence_sources(assessment, current) is None


def test_reasoning_detector_penalizes_and_feedback_appears_only_after_detection(tmp_path):
    observations = {"A": [], "B": []}
    clients = {"A": _agent("a", observations["A"]),
               "B": _agent("b", observations["B"]),
               "detector": _detector(_assessment(detected=True))}
    cfg = StudyConfig(horizon=2, study="study2", private_memory=True, winner_p1=True,
                      regulation=Regulation(mode="llm_reasoning", penalty_fraction=.5))
    out = tmp_path / "regulated"
    run(cfg, out, clients=clients)
    rows = load_rounds(out)
    assert rows[0]["detected"] is True
    assert rows[0]["gross_profit"]["A"] == 2000
    assert rows[0]["net_profit"]["A"] == 1000
    assert "collusion detected" not in observations["A"][0].lower()
    assert "collusion detected = yes" in observations["A"][1].lower()
    assert "reason for penalty = observed collusion" in observations["A"][1].lower()
    calls = [json.loads(x) for x in (out / "detector_calls.jsonl").read_text().splitlines()]
    assert len(calls) == 2 and all(x["parse_ok"] for x in calls)


def test_detector_failure_stops_and_marks_run_failed(tmp_path):
    observations = {"A": [], "B": []}
    clients = {"A": _agent("a", observations["A"]),
               "B": _agent("b", observations["B"]),
               "detector": _detector({"invalid": True})}
    cfg = StudyConfig(horizon=1, study="study2",
                      regulation=Regulation(mode="llm_reasoning"))
    out = tmp_path / "failed"
    with pytest.raises(DetectorFailure):
        run(cfg, out, clients=clients)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["analysis_eligible"] is False
    assert not load_rounds(out)
