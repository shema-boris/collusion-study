"""Complete JSONL logging (protocol Section 13). Named ``runlog`` to avoid shadowing stdlib logging.

Two streams per run directory:
    rounds.jsonl     one RoundRecord per completed round (outcome + reasoning + market averages)
    llm_calls.jsonl  every bidding-agent call
    detector_calls.jsonl  every Study 2 detector call (empty in Study 1)
    manifest.json    run-level identity + frozen config (Section 13 run-level fields)

Writes are flushed per line so a crash keeps all prior rounds; a run is resumable by replaying
rounds.jsonl.
"""
from __future__ import annotations

import json
import threading
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
    units: dict[str, float]
    gross_profit: dict[str, float]
    penalty_status: dict[str, bool]             # Study 1: always {"A": False, "B": False}
    penalty_amount: dict[str, float]
    net_profit: dict[str, float]
    cumulative_profit: dict[str, float]
    joint_average: float                        # M_t = (P_A + P_B) / 2
    rolling_average: Optional[float]            # R_t over the detector window (informational in Study 1)
    detected: bool                              # Study 1: always False
    reasoning: dict[str, str] = field(default_factory=dict)
    plans: dict[str, str] = field(default_factory=dict)
    insights: dict[str, str] = field(default_factory=dict)
    unprocured_units: float = 0.0
    detector_assessment: Optional[dict] = None

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
        self._detector = open(self.run_dir / "detector_calls.jsonl", mode, encoding="utf-8")
        self._write_lock = threading.Lock()
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
        # Alpha and Beta calls run concurrently; keep each JSONL record atomic.
        with self._write_lock:
            self._llm.write(json.dumps(call) + "\n")
            self._llm.flush()

    def log_detector_call(self, call: dict) -> None:
        self._detector.write(json.dumps(call) + "\n")
        self._detector.flush()

    def update_manifest(self, **updates) -> None:
        self.manifest.update(updates)
        self._write_manifest()

    def write_prehistory(self, rounds: list[dict]) -> None:
        """Store synthetic context separately from model-generated outcomes."""
        (self.run_dir / "prehistory.json").write_text(
            json.dumps(rounds, indent=2), encoding="utf-8")

    def close(self) -> None:
        for h in (self._rounds, self._llm, self._detector):
            try:
                h.close()
            except Exception:
                pass


def load_rounds(run_dir: str | Path) -> list[dict]:
    path = Path(run_dir) / "rounds.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_prehistory(run_dir: str | Path) -> list[dict]:
    path = Path(run_dir) / "prehistory.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
