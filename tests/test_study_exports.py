import csv
import json
from pathlib import Path

from study.export_csv import export_rounds, flatten_round
from study.export_results import build_dataset


def _record(round_number: int, *, detected: bool = False) -> dict:
    assessment = None
    if detected:
        assessment = {
            "alpha_coordination_intent": True,
            "beta_coordination_intent": True,
            "mutual_alignment": True,
            "competitive_explanation": False,
            "classification": "mutual_price_coordination",
            "coordination_objective": "hold a shared bid",
            "alpha_evidence": [{"source": "plan", "excerpt": "hold"}],
            "beta_evidence": [{"source": "plan", "excerpt": "match"}],
            "summary": "aligned",
            "decision_rule_version": "reasoning_mutual_v1",
            "response_json_repaired": False,
        }
    gross = {"A": 100.0, "B": 100.0}
    penalty = {"A": 50.0 if detected else 0.0, "B": 50.0 if detected else 0.0}
    net = {agent: gross[agent] - penalty[agent] for agent in ("A", "B")}
    return {
        "round_number": round_number,
        "phase": "early",
        "bids": {"A": 12.0, "B": 12.0},
        "winner": None,
        "units": {"A": 50.0, "B": 50.0},
        "gross_profit": gross,
        "penalty_status": {"A": detected, "B": detected},
        "penalty_amount": penalty,
        "net_profit": net,
        "cumulative_profit": {"A": net["A"] * round_number,
                              "B": net["B"] * round_number},
        "joint_average": 12.0,
        "rolling_average": 12.0,
        "detected": detected,
        "reasoning": {"A": "reason A", "B": "reason B"},
        "plans": {"A": "hold", "B": "match"},
        "insights": {"A": "insight A", "B": "insight B"},
        "unprocured_units": 0.0,
        "detector_assessment": assessment,
    }


def test_flatten_round_includes_detector_and_penalty_fields():
    row = flatten_round(_record(1, detected=True))
    assert row["winner"] == "tie"
    assert row["gross_profit_alpha"] == 100.0
    assert row["penalty_amount_alpha"] == 50.0
    assert row["round_profit_alpha"] == 50.0
    assert row["detector_classification"] == "mutual_price_coordination"
    assert json.loads(row["alpha_detector_evidence"])[0]["excerpt"] == "hold"


def test_export_rounds_writes_excel_compatible_csv(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "rounds.jsonl").write_text(
        json.dumps(_record(1)) + "\n", encoding="utf-8")
    output = export_rounds(run_dir)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["reasoning_alpha"] == "reason A"


def test_build_dataset_validates_and_exports_canonical_run(tmp_path: Path):
    run_dir = tmp_path / "raw" / "run"
    run_dir.mkdir(parents=True)
    manifest = {
        "study": "study2",
        "status": "completed",
        "analysis_eligible": True,
        "seed": 0,
        "horizon": 2,
        "models": {"A": "model/a", "B": "model/a"},
        "market": {"type": "winner_take_all"},
        "regulation": {"detector_model": "judge", "penalty_fraction": 0.5},
        "detector_design": {"prompt_version": "v2", "decision_rule": "rule"},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "rounds.jsonl").write_text(
        "\n".join(json.dumps(_record(number, detected=number == 2))
                  for number in (1, 2)) + "\n", encoding="utf-8")
    config = tmp_path / "canonical.yaml"
    config.write_text(
        "runs:\n"
        "  - id: test_run\n"
        "    model_family: Test\n"
        "    treatment: reasoning_detector_penalty50\n"
        "    market: winner_take_all\n"
        "    comparison_rounds: 2\n"
        "    run_dir: raw/run\n",
        encoding="utf-8",
    )
    output = tmp_path / "dataset"
    build_dataset(config, output, tmp_path)
    with (output / "run_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        summary = next(csv.DictReader(handle))
    assert summary["detections"] == "1"
    assert summary["joint_net_profit"] == "300.0"
    assert (output / "manifests" / "test_run.json").exists()
