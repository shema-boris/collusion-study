# collusion-study

Adversarial co-evolution of collusion and detection in multi-agent LLM systems.

Two fixed (non-fine-tuned) LLM agents repeatedly bid in a first-price procurement
auction. They adapt only through a shared interaction history. A co-evolving detector
tries to catch coordination. We ask whether oversight discourages collusion or instead
drives subtler, detection-evading coordination.

See [docs/DESIGN.md](docs/DESIGN.md) for the full specification of record.

## Status

Deterministic core implemented and tested (no LLM required yet):

- `src/core/` — shared data models (`state.py`) and the `run_round()` orchestrator
  (`round.py`), with LLM nodes injected as callables.
- `src/auction/` — cost generation, first-price + quality-gate winner selection,
  payoffs, and the competitive equilibrium baseline `b(c) = (c + 60) / 2`.
- `src/history/` — raw per-round storage and the condition-aware **blind / informed**
  renderers (structural leak prevention: blind views never expose detector confidence).
- `configs/` — all tunable parameters (rounds, seeds, gate, CFS coefficients, detector K).

Not yet implemented: the LLM-backed agent / judge / detector nodes, calibration runs,
and offline metrics.

## Setup

```bash
pip install -r requirements.txt
python -m pytest -q
```
