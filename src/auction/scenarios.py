"""Scenario bank: a fixed, indexed dataset of procurement briefs (DESIGN.md §2).

Deterministic by design -- round N always maps to scenario N via ``repository.get(N)``.
No sampling, no RNG, no shuffling: the scenarios themselves supply the variation, and a
fixed mapping holds the scenario constant across ALL conditions AND seeds, so it is a
fully-controlled factor rather than a source of randomness. Randomness lives only where it
must -- private costs and tie-breaks (see ``auction.environment``).
"""
from __future__ import annotations

from pathlib import Path

from core.state import Scenario
from utils.config import load_yaml


class ScenarioRepository:
    def __init__(self, scenarios: list[Scenario]):
        if not scenarios:
            raise ValueError("scenario bank is empty")
        ids = [s.id for s in scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate scenario ids in bank")
        self._scenarios = list(scenarios)

    @classmethod
    def load(cls, path: str | Path) -> "ScenarioRepository":
        raw = load_yaml(path)
        items = raw["scenarios"] if isinstance(raw, dict) else raw
        return cls([Scenario(**d) for d in items])

    def __len__(self) -> int:
        return len(self._scenarios)

    def get(self, round_number: int) -> Scenario:
        """Round N (1-indexed) -> scenario N. Fail fast if the bank is too small."""
        idx = round_number - 1
        if idx < 0 or idx >= len(self._scenarios):
            raise IndexError(
                f"round {round_number} has no scenario: bank holds {len(self._scenarios)} "
                f"(one per round, no repetition -- DESIGN §2)"
            )
        return self._scenarios[idx]

    def all(self) -> list[Scenario]:
        return list(self._scenarios)
