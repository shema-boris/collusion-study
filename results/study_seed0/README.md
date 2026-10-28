# Canonical seed-0 study dataset

This directory is the Git-friendly export of the 20 canonical runs used in the
five-model mentor report: five model families × two market mechanisms × two
regulatory treatments. The data are exploratory because only seed 0 is complete.

## Files

- `all_rounds.csv` — one row per recorded round, including bids, allocations,
  gross and net profits, penalties, detector decisions, reasoning, private plans,
  and private insights. It retains Kimi smooth rounds 101–160 but marks them
  `included_in_matched_comparison=false`.
- `run_summary.csv` — matched 100-round metrics for each of the 20 cells.
- `run_index.csv` — model, market, treatment, seed, source path, horizon, and
  detector-version provenance.
- `manifests/` — the exact run manifest for each canonical experiment.
- `dataset_manifest.json` — dataset-level schema and row counts.

The CSVs use UTF-8 with a byte-order mark, so they open cleanly in Excel while
remaining compatible with Python, R, and Google Sheets.

## Regenerate

From the repository root, after the raw `runs_study/` directory is available:

```powershell
.\.venv\Scripts\python.exe -m study.export_results
```

The canonical source paths and matched horizons are frozen in
`configs/canonical_study_runs.yaml`. The exporter fails if a source run is
missing, incomplete, or has a conflicting market configuration.

## Interpretation warning

These are single-seed trajectories, not population estimates. Detector labels
are outputs of the online GPT-5.2 regulator and are not human-validated ground
truth. Use bids, payoffs, counterfactual incentives, temporal patterns, and
agent-generated text together when interpreting coordination.

The unregulated Kimi smooth run contains 160 rounds, but only rounds 1–100 enter
the matched comparison because agents were not told the horizon. This truncation
is explicit in the `comparison_rounds` and `included_in_matched_comparison`
columns.
