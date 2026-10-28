"""Build the curated, shareable dataset for the canonical Study 1/2 runs.

Usage:
    python -m study.export_results

The command validates every configured run, exports every recorded round to a
single UTF-8-with-BOM CSV, computes matched-horizon summaries, and copies the
small run manifests.  Raw LLM transport logs remain local because they are
large working artifacts; all submitted reasoning, plans, insights, detector
decisions, market outcomes, and penalties are present in ``all_rounds.csv``.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
from pathlib import Path

import yaml

from study.export_csv import FIELDS, flatten_round


METADATA_FIELDS = [
    "run_id", "model_family", "treatment", "regulated", "market", "seed",
    "model_alpha", "model_beta", "source_run_dir", "configured_horizon",
    "comparison_rounds", "included_in_matched_comparison",
]

INDEX_FIELDS = [
    "run_id", "model_family", "treatment", "regulated", "market", "seed",
    "model_alpha", "model_beta", "source_run_dir", "status", "analysis_eligible",
    "configured_horizon", "recorded_rounds", "comparison_rounds", "detector_model",
    "detector_prompt_version", "detector_decision_rule", "penalty_fraction",
]

SUMMARY_FIELDS = [
    "run_id", "model_family", "treatment", "regulated", "market", "seed",
    "comparison_rounds", "mean_bid", "median_bid", "minimum_bid", "maximum_bid",
    "exact_ties", "near_ties_10_cents", "alpha_wins", "beta_wins", "detections",
    "possible_evasion_classifications", "joint_gross_profit", "total_penalty",
    "joint_net_profit", "final_cumulative_profit_alpha", "final_cumulative_profit_beta",
]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summary(spec: dict, manifest: dict, records: list[dict]) -> dict:
    limit = int(spec["comparison_rounds"])
    matched = [record for record in records if int(record["round_number"]) <= limit]
    if len(matched) != limit:
        raise ValueError(
            f"{spec['id']}: expected {limit} matched rounds, found {len(matched)}")

    bids = [float(record["bids"][agent]) for record in matched for agent in ("A", "B")]
    exact_ties = sum(abs(float(r["bids"]["A"]) - float(r["bids"]["B"])) < 1e-9
                     for r in matched)
    near_ties = sum(abs(float(r["bids"]["A"]) - float(r["bids"]["B"])) <= 0.10 + 1e-9
                    for r in matched)
    gross = sum(sum(float(value) for value in (r.get("gross_profit") or
                                                r["net_profit"]).values()) for r in matched)
    penalties = sum(sum(float(value) for value in
                        (r.get("penalty_amount") or {"A": 0, "B": 0}).values())
                    for r in matched)
    net = sum(sum(float(value) for value in r["net_profit"].values()) for r in matched)
    last = matched[-1]
    return {
        "run_id": spec["id"],
        "model_family": spec["model_family"],
        "treatment": spec["treatment"],
        "regulated": spec["treatment"] != "unregulated",
        "market": spec["market"],
        "seed": manifest.get("seed", ""),
        "comparison_rounds": limit,
        "mean_bid": round(sum(bids) / len(bids), 4),
        "median_bid": round(statistics.median(bids), 4),
        "minimum_bid": round(min(bids), 4),
        "maximum_bid": round(max(bids), 4),
        "exact_ties": exact_ties,
        "near_ties_10_cents": near_ties,
        "alpha_wins": sum(r.get("winner") == "A" for r in matched),
        "beta_wins": sum(r.get("winner") == "B" for r in matched),
        "detections": sum(bool(r.get("detected")) for r in matched),
        "possible_evasion_classifications": sum(
            (r.get("detector_assessment") or {}).get("classification") == "possible_evasion"
            for r in matched),
        "joint_gross_profit": round(gross, 2),
        "total_penalty": round(penalties, 2),
        "joint_net_profit": round(net, 2),
        "final_cumulative_profit_alpha": round(last["cumulative_profit"]["A"], 2),
        "final_cumulative_profit_beta": round(last["cumulative_profit"]["B"], 2),
    }


def build_dataset(config_path: Path, output_dir: Path, project_root: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    specs = config.get("runs") or []
    if not specs:
        raise ValueError(f"no runs configured in {config_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir = output_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    index_rows: list[dict] = []
    summary_rows: list[dict] = []

    for spec in specs:
        run_dir = project_root / spec["run_dir"]
        manifest_path = run_dir / "manifest.json"
        rounds_path = run_dir / "rounds.jsonl"
        if not manifest_path.exists() or not rounds_path.exists():
            raise FileNotFoundError(f"canonical run is incomplete: {run_dir}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = _read_jsonl(rounds_path)
        if manifest.get("status") != "completed":
            raise ValueError(f"{spec['id']}: manifest status is not completed")
        if (manifest.get("market") or {}).get("type") != spec["market"]:
            raise ValueError(f"{spec['id']}: configured market disagrees with manifest")

        regulated = spec["treatment"] != "unregulated"
        models = manifest.get("models") or {}
        regulation = manifest.get("regulation") or {}
        detector_design = manifest.get("detector_design") or {}
        metadata = {
            "run_id": spec["id"],
            "model_family": spec["model_family"],
            "treatment": spec["treatment"],
            "regulated": regulated,
            "market": spec["market"],
            "seed": manifest.get("seed", ""),
            "model_alpha": models.get("A", ""),
            "model_beta": models.get("B", ""),
            "source_run_dir": spec["run_dir"],
            "configured_horizon": manifest.get("horizon", ""),
            "comparison_rounds": spec["comparison_rounds"],
        }
        for record in records:
            all_rows.append({
                **metadata,
                "included_in_matched_comparison": (
                    int(record["round_number"]) <= int(spec["comparison_rounds"])),
                **flatten_round(record),
            })

        index_rows.append({
            **metadata,
            "status": manifest.get("status", ""),
            "analysis_eligible": manifest.get("analysis_eligible", True),
            "recorded_rounds": len(records),
            "detector_model": regulation.get("detector_model", ""),
            "detector_prompt_version": detector_design.get("prompt_version", ""),
            "detector_decision_rule": detector_design.get("decision_rule", ""),
            "penalty_fraction": regulation.get("penalty_fraction", ""),
        })
        summary_rows.append(_summary(spec, manifest, records))
        shutil.copyfile(manifest_path, manifests_dir / f"{spec['id']}.json")

    _write_csv(output_dir / "all_rounds.csv", METADATA_FIELDS + FIELDS, all_rows)
    _write_csv(output_dir / "run_index.csv", INDEX_FIELDS, index_rows)
    _write_csv(output_dir / "run_summary.csv", SUMMARY_FIELDS, summary_rows)
    (output_dir / "dataset_manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "canonical_run_config": config_path.as_posix(),
        "run_count": len(specs),
        "recorded_round_count": len(all_rows),
        "matched_round_count": sum(int(spec["comparison_rounds"]) for spec in specs),
        "notes": [
            "CSV files use UTF-8 with BOM for Excel compatibility.",
            "all_rounds.csv includes full submitted reasoning, plans, and insights.",
            "Rows beyond comparison_rounds are retained but marked outside the matched comparison.",
            "Raw API transport logs are not included in this curated Git dataset.",
        ],
    }, indent=2), encoding="utf-8")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path("configs/canonical_study_runs.yaml"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("results/study_seed0"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    build_dataset(args.config, args.output_dir, args.project_root)
    print(args.output_dir)


if __name__ == "__main__":
    main()
