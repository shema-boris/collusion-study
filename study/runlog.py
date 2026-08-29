"""Complete JSONL logging (protocol Section 13). Named ``runlog`` to avoid shadowing stdlib logging.

Two streams per run directory:
    rounds.jsonl     one RoundRecord per completed round (outcome + reasoning + market averages)
    llm_calls.jsonl  every agent call: observation, raw response, parsed bid, parse/API status
    manifest.json    run-level identity + frozen config (Section 13 run-level fields)

Writes are flushed per line so a crash keeps all prior rounds; a run is resumable by replaying
rounds.jsonl.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


def phase_of(round_number: int, horizon: int = 60) -> str:
    """Protocol Section 3 timeline (scaled if horizon != 60): early / repeated / late."""
    frac = round_number / max(horizon, 1)
    if frac <= 0.25:
        return "early"
    if frac <= 0.583:      # 35/60
        return "repeated"
    return "late"


@dataclass
class RoundRecord:
    """One completed round (Section 13). Profit fields are per-firm dicts keyed 'A'/'B'."""
    round_number: int
    phase: str
    bids: dict[str, float]
    winner: Optional[str]                       # "A", "B", or None (tie)
    units: dict[str, int]
    gross_profit: dict[str, float]
    penalty_status: dict[str, bool]             # Study 1: always {"A": False, "B": False}
    penalty_amount: dict[str, float]
    net_profit: dict[str, float]
    cumulative_profit: dict[str, float]
    joint_average: float                        # M_t = (P_A + P_B) / 2
    rolling_average: Optional[float]            # R_t over the detector window (informational in Study 1)
    detected: bool                              # Study 1: always False
    reasoning: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class RunLogger:
    """Append-only JSONL writer for one (config, seed) run."""

    def __init__(self, run_dir: Path, manifest: dict, *, append: bool):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        self._rounds = open(self.run_dir / "rounds.jsonl", mode, encoding="utf-8")
        self._llm = open(self.run_dir / "llm_calls.jsonl", mode, encoding="utf-8")
        self.manifest = manifest
        self._write_manifest()

    @classmethod
    def create(cls, run_dir: str | Path, manifest: dict) -> "RunLogger":
        return cls(Path(run_dir), manifest, append=False)   # fresh: truncate any stale files

    @classmethod
    def resume(cls, run_dir: str | Path, manifest: dict) -> tuple["RunLogger", list[dict]]:
        run_dir = Path(run_dir)
        prior = load_rounds(run_dir)
        return cls(run_dir, manifest, append=True), prior

    def _write_manifest(self) -> None:
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    def log_round(self, rec: RoundRecord) -> None:
        self._rounds.write(rec.to_json() + "\n")
        self._rounds.flush()

    def log_llm_call(self, call: dict) -> None:
        self._llm.write(json.dumps(call) + "\n")
        self._llm.flush()

    def update_manifest(self, **updates) -> None:
        self.manifest.update(updates)
        self._write_manifest()

    def close(self) -> None:
        for h in (self._rounds, self._llm):
            try:
                h.close()
            except Exception:
                pass


def load_rounds(run_dir: str | Path) -> list[dict]:
    path = Path(run_dir) / "rounds.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
