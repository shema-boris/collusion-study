"""Scenario bank: a fixed, indexed dataset of procurement briefs (DESIGN.md §2).

The bank is sorted, so its economics (reference, costs) rise with the index. Playing it in
raw index order (round N -> scenario N) would make every economic quantity climb monotonically
with the round number -- a confound that masquerades as bid escalation. So each run walks the
bank in a **seeded permutation** (``ordered_provider(seed)``): the order is deterministic per
seed (reproducible), shared across ALL conditions with that seed (so R0/C1/S/A stay comparable
round-by-round), and varies between seeds (independent replicates). This decorrelates economics
from the round index while keeping the scenario a fully-controlled factor. ``get(N)`` still
gives the raw index-ordered mapping for tests and the sequential fallback. Randomness otherwise
lives only where it must -- private costs and tie-breaks (see ``auction.environment``).
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Callable

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

    def order(self, seed: int, *, shuffle: bool = True) -> list[int]:
        """The 0-based scenario indices in the order this (seed) walks the bank.

        A seeded permutation of ``range(len(self))``: deterministic per seed and stable across
        Python versions (``random.Random`` uses a fixed Mersenne Twister + shuffle). ``shuffle
        =False`` returns the raw index order (the sequential fallback).
        """
        idx = list(range(len(self._scenarios)))
        if shuffle:
            random.Random(seed).shuffle(idx)
        return idx

    def ordered_provider(self, seed: int, *, shuffle: bool = True) -> Callable[[int], Scenario]:
        """Return a ``round_number -> Scenario`` provider that walks the bank in ``order(seed)``.

        Round N (1-indexed) -> scenario at position N in the seeded order. Fails fast if the run
        asks for more rounds than the bank holds (one scenario per round, no repetition, §2).
        """
        order = self.order(seed, shuffle=shuffle)

        def provider(round_number: int) -> Scenario:
            pos = round_number - 1
            if pos < 0 or pos >= len(order):
                raise IndexError(
                    f"round {round_number} has no scenario: bank holds {len(order)} "
                    f"(one per round, no repetition -- DESIGN §2)"
                )
            return self._scenarios[order[pos]]

        return provider

    def all(self) -> list[Scenario]:
        return list(self._scenarios)
