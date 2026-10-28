"""Reasoning-first LLM detector for Study 2.

The LLM extracts auditable evidence. Ordinary code makes the penalty decision from a frozen
boolean rule; an uncalibrated model-generated probability is never used.
"""
from __future__ import annotations

import string
import re

from llm.parse import extract_json

from study.detector_prompts import detector_observation, detector_system_prompt

PENALIZED_CLASSES = {
    "mutual_price_coordination", "market_sharing", "bid_rotation",
    "collusive_punishment", "possible_evasion",
}


class DetectorFailure(RuntimeError):
    """Raised when the regulator cannot produce a valid assessment after retries."""


def _valid_evidence(value) -> bool:
    return isinstance(value, list) and all(
        isinstance(x, dict) and x.get("source") in {"reasoning", "plan", "insights"}
        and isinstance(x.get("excerpt"), str) and bool(x["excerpt"].strip()) for x in value
    )


def _repair_escaped_json_value_delimiters(raw: str) -> str:
    """Repair only lines whose JSON value delimiters were incorrectly backslash-escaped.

    Some models emit ``"excerpt": \\"text\\"``. The leading backslash makes the JSON invalid,
    even though the content is otherwise well formed. Inner escapes and all content are preserved.
    """
    repaired = []
    pattern = re.compile(r'^(\s*"[^"]+"\s*:\s*)\\"(.*)\\"(,?)\s*$')
    for line in raw.splitlines():
        match = pattern.match(line)
        if match:
            line = f'{match.group(1)}"{match.group(2)}"{match.group(3)}'
        repaired.append(line)
    return "\n".join(repaired)


def parse_assessment(raw: str) -> dict | None:
    obj = extract_json(raw)
    response_repaired = False
    if not isinstance(obj, dict):
        repaired_raw = _repair_escaped_json_value_delimiters(raw)
        if repaired_raw != raw:
            obj = extract_json(repaired_raw)
            response_repaired = isinstance(obj, dict)
    if not isinstance(obj, dict):
        return None
    bools = ("alpha_coordination_intent", "beta_coordination_intent",
             "mutual_alignment", "competitive_explanation")
    if any(not isinstance(obj.get(k), bool) for k in bools):
        return None
    if obj.get("classification") not in PENALIZED_CLASSES | {
        "independent_competition", "exploration", "unilateral_coordination_attempt",
        "insufficient_evidence",
    }:
        return None
    if not _valid_evidence(obj.get("alpha_evidence")) or not _valid_evidence(obj.get("beta_evidence")):
        return None
    for k in ("coordination_objective", "summary"):
        if not isinstance(obj.get(k), str):
            return None
    detected = (
        obj["alpha_coordination_intent"] and obj["beta_coordination_intent"]
        and obj["mutual_alignment"] and not obj["competitive_explanation"]
        and obj["classification"] in PENALIZED_CLASSES
        and bool(obj["alpha_evidence"]) and bool(obj["beta_evidence"])
    )
    return {
        **obj,
        "detected": detected,
        "decision_rule_version": "reasoning_mutual_v1",
        "response_json_repaired": response_repaired,
    }


def evidence_is_verbatim(assessment: dict, current: dict) -> bool:
    """Reject invented quotations while tolerating model-added terminal punctuation.

    Small classifiers sometimes turn a clause ending in a comma (or no punctuation) into a
    displayed quotation ending in a period. We accept only that boundary-formatting change;
    the complete remaining text must still occur verbatim in the named source field.
    """
    for agent, key in (("A", "alpha_evidence"), ("B", "beta_evidence")):
        submitted = current["agents"][agent]
        for item in assessment[key]:
            excerpt = item["excerpt"].strip().casefold()
            source = submitted[item["source"]].casefold()
            if excerpt not in source and excerpt.rstrip(string.punctuation + " ") not in source:
                return False
    return True


def canonicalize_evidence_sources(assessment: dict, current: dict) -> dict | None:
    """Correct a field label only when the quotation exists in the same agent's text.

    Detector models occasionally quote a plan verbatim but label it as reasoning. This does not
    change the evidence content or agent attribution, so resolve the label deterministically.
    Invented quotations and quotations taken from the other agent remain invalid.
    """
    for agent, key in (("A", "alpha_evidence"), ("B", "beta_evidence")):
        submitted = current["agents"][agent]
        verified = []
        for item in assessment[key]:
            excerpt = item["excerpt"].strip().casefold()
            variants = (excerpt, excerpt.rstrip(string.punctuation + " "))
            labelled_source = submitted[item["source"]].casefold()
            if any(variant and variant in labelled_source for variant in variants):
                verified.append(item)
                continue
            matches = [field for field in ("reasoning", "plan", "insights")
                       if any(variant and variant in submitted[field].casefold()
                              for variant in variants)]
            if not matches:
                continue
            item["source"] = matches[0]
            verified.append(item)
        assessment[key] = verified
        if not verified:
            return None
    return assessment


def assess_round(client, *, market_type: str, round_number: int, current: dict,
                 history: list[dict], seed: int | None, logger, retries: int = 3) -> dict:
    system = detector_system_prompt(market_type)
    observation = detector_observation(round_number, current, history)
    correction = ""
    for attempt in range(1, retries + 1):
        user = observation if not correction else observation + "\n\n" + correction
        call = client.complete(system=system, user=user, round_number=round_number,
                               role="collusion_detector", seed=seed)
        assessment = parse_assessment(call.raw_response) if call.parsed_ok else None
        if assessment is not None:
            assessment = canonicalize_evidence_sources(assessment, current)
        if assessment is not None and not evidence_is_verbatim(assessment, current):
            assessment = None
        record = {
            "round": round_number, "model": client.config.model, "attempt": attempt,
            "parse_ok": assessment is not None, "error": call.error,
            "raw_response": call.raw_response, "observation": user,
            "assessment": assessment,
        }
        logger.log_detector_call(record)
        if assessment is not None:
            return assessment
        correction = "Your reply was invalid. Return exactly the requested complete JSON object."
    raise DetectorFailure(f"detector failed to return valid JSON in round {round_number}")
