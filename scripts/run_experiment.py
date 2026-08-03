"""CLI entry point for a single (condition, seed) run.

Examples:
    export OPENROUTER_API_KEY=sk-or-...
    python scripts/run_experiment.py --condition C1 --seed 0 --rounds 20
    python scripts/run_experiment.py --condition A_blind --seed 0 --rounds 50 --resume
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
