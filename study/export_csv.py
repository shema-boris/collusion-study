"""Export one study run to an Excel-compatible, analysis-ready CSV file.

The JSONL logs remain the lossless source of truth.  This exporter flattens the
nested market, private-memory, and detector fields so collaborators can inspect
the run in Excel, Google Sheets, R, pandas, or another tabular tool.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "round_number", "phase", "winner", "bid_alpha", "bid_beta", "units_alpha",
    "units_beta", "unprocured_units", "gross_profit_alpha", "gross_profit_beta",
    "penalty_status_alpha", "penalty_status_beta", "penalty_amount_alpha",
    "penalty_amount_beta", "round_profit_alpha", "round_profit_beta",
    "cumulative_profit_alpha", "cumulative_profit_beta", "joint_average",
    "rolling_average", "detected", "detector_classification",
    "alpha_coordination_intent", "beta_coordination_intent", "mutual_alignment",
    "competitive_explanation", "coordination_objective", "detector_summary",
    "alpha_detector_evidence", "beta_detector_evidence", "detector_decision_rule",
    "detector_response_json_repaired",
    "reasoning_alpha", "reasoning_beta", "plan_alpha", "plan_beta", "insights_alpha",
    "insights_beta",
]


def _agent(record: dict, field: str, agent: str, default=""):
    return (record.get(field) or {}).get(agent, default)


def flatten_round(record: dict) -> dict:
    """Return one flat row while tolerating legacy Study 1 records."""
    assessment = record.get("detector_assessment") or {}
    winner = record.get("winner")
    return {
        "round_number": record["round_number"],
        "phase": record.get("phase", ""),
        "winner": winner if winner is not None else "tie",
        "bid_alpha": _agent(record, "bids", "A"),
        "bid_beta": _agent(record, "bids", "B"),
        "units_alpha": _agent(record, "units", "A"),
        "units_beta": _agent(record, "units", "B"),
        "unprocured_units": record.get("unprocured_units", 0),
        "gross_profit_alpha": _agent(record, "gross_profit", "A",
                                      _agent(record, "net_profit", "A")),
        "gross_profit_beta": _agent(record, "gross_profit", "B",
                                     _agent(record, "net_profit", "B")),
        "penalty_status_alpha": _agent(record, "penalty_status", "A", False),
        "penalty_status_beta": _agent(record, "penalty_status", "B", False),
        "penalty_amount_alpha": _agent(record, "penalty_amount", "A", 0),
        "penalty_amount_beta": _agent(record, "penalty_amount", "B", 0),
        # Historical name retained for compatibility; these are net profits.
        "round_profit_alpha": _agent(record, "net_profit", "A"),
        "round_profit_beta": _agent(record, "net_profit", "B"),
        "cumulative_profit_alpha": _agent(record, "cumulative_profit", "A"),
        "cumulative_profit_beta": _agent(record, "cumulative_profit", "B"),
        "joint_average": record.get("joint_average", ""),
        "rolling_average": record.get("rolling_average", ""),
        "detected": record.get("detected", False),
        "detector_classification": assessment.get("classification", ""),
        "alpha_coordination_intent": assessment.get("alpha_coordination_intent", ""),
        "beta_coordination_intent": assessment.get("beta_coordination_intent", ""),
        "mutual_alignment": assessment.get("mutual_alignment", ""),
        "competitive_explanation": assessment.get("competitive_explanation", ""),
        "coordination_objective": assessment.get("coordination_objective", ""),
        "detector_summary": assessment.get("summary", ""),
        "alpha_detector_evidence": json.dumps(
            assessment.get("alpha_evidence", []), ensure_ascii=False),
        "beta_detector_evidence": json.dumps(
            assessment.get("beta_evidence", []), ensure_ascii=False),
        "detector_decision_rule": assessment.get("decision_rule_version", ""),
        "detector_response_json_repaired": assessment.get("response_json_repaired", ""),
        "reasoning_alpha": _agent(record, "reasoning", "A"),
        "reasoning_beta": _agent(record, "reasoning", "B"),
        "plan_alpha": _agent(record, "plans", "A"),
        "plan_beta": _agent(record, "plans", "B"),
        "insights_alpha": _agent(record, "insights", "A"),
        "insights_beta": _agent(record, "insights", "B"),
    }


def export_rounds(run_dir: str | Path, output: str | Path | None = None) -> Path:
    run_dir = Path(run_dir)
    source = run_dir / "rounds.jsonl"
    destination = Path(output) if output else run_dir / "rounds.csv"
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
               if line.strip()]

    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(flatten_round(record))
    return destination


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    print(export_rounds(args.run_dir, args.output))


if __name__ == "__main__":
    main()
