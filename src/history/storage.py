"""Run logging: capture EVERYTHING produced while an experiment runs (DESIGN.md §12).

Local, append-only, crash-safe files -- the canonical, reproducible record the analysis and
the paper depend on (independent of any tracing/observability overlay). Layout per run
(one condition x one seed):

    runs/<experiment>/<condition>__seed<seed>/
        manifest.json     run metadata + live status/progress (last_round)
        rounds.jsonl      one RoundRecord per line -- the append-only archive
        llm_calls.jsonl   every LLM prompt/response/usage, tagged by round + role
        events.jsonl      lifecycle, warnings, parse failures, errors

Every write is stream-flushed, so a crash keeps all prior rounds. Metrics are NOT computed
here -- raw data only, analysed offline (DESIGN.md §9).
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.state import Condition, LLMCall, RoundRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_commit() -> Optional[str]:
    """Best-effort code version for the manifest; None if git is unavailable."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
    except Exception:
        return None


def run_dir_name(condition_name: str, seed: int) -> str:
    return f"{condition_name}__seed{seed}"


class RunLogger:
    """Append-only writer for a single run. Use as a context manager for safe finalize."""

    def __init__(self, run_dir: Path, manifest: dict, *, append: bool = True):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest
        # append=True for resume (keep prior rounds); False for a fresh create, which MUST
        # truncate any stale rounds.jsonl in a reused dir -- else the new run is silently
        # concatenated onto old data (contaminating analysis).
        mode = "a" if append else "w"
        self._rounds = open(self.run_dir / "rounds.jsonl", mode, encoding="utf-8")
        self._llm = open(self.run_dir / "llm_calls.jsonl", mode, encoding="utf-8")
        self._events = open(self.run_dir / "events.jsonl", mode, encoding="utf-8")
        self._write_manifest()

    # --- construction -------------------------------------------------------
    @classmethod
    def create(cls, runs_root: str | Path, *, condition: Condition, seed: int,
               planned_rounds: int, config: Optional[dict] = None,
               models: Optional[dict] = None, experiment: Optional[str] = None) -> "RunLogger":
        run_dir = Path(runs_root) / run_dir_name(condition.name, seed)
        manifest = {
            "experiment": experiment,
            "condition": condition.model_dump(),
            "seed": seed,
            "planned_rounds": planned_rounds,
            "config": config or {},
            "models": models or {},
            "git_commit": git_commit(),
            "created_at": _now(),
            "updated_at": _now(),
            "status": "running",
            "last_round": 0,
        }
        return cls(run_dir, manifest, append=False)  # fresh run: truncate any stale files

    @classmethod
    def resume(cls, runs_root: str | Path, *, condition: Condition, seed: int,
               planned_rounds: int, **create_kwargs) -> tuple["RunLogger", list[RoundRecord]]:
        """Reopen an existing run and return (logger, prior rounds) to rehydrate state.

        Resume = replay ``rounds.jsonl`` (DESIGN.md §7/§12); we do not rely on any framework
        checkpoint. If the run does not exist yet, this behaves like ``create``.
        """
        run_dir = Path(runs_root) / run_dir_name(condition.name, seed)
        prior = cls.load_rounds(run_dir)
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "running"
            manifest["last_round"] = prior[-1].round_number if prior else 0
            return cls(run_dir, manifest), prior
        return cls.create(runs_root, condition=condition, seed=seed,
                          planned_rounds=planned_rounds, **create_kwargs), prior

    # --- logging ------------------------------------------------------------
    def log_round(self, rec: RoundRecord) -> None:
        self._rounds.write(rec.model_dump_json() + "\n")
        self._rounds.flush()
        self.manifest["last_round"] = rec.round_number
        self._write_manifest()

    def log_llm_call(self, call: LLMCall) -> None:
        self._llm.write(call.model_dump_json() + "\n")
        self._llm.flush()

    def log_event(self, level: str, message: str, **data) -> None:
        rec = {"ts": _now(), "level": level, "message": message, **data}
        self._events.write(json.dumps(rec) + "\n")
        self._events.flush()

    def finalize(self, status: str = "completed") -> None:
        self.manifest["status"] = status
        self._write_manifest()
        self.close()

    def close(self) -> None:
        for handle in (self._rounds, self._llm, self._events):
            try:
                handle.close()
            except Exception:
                pass

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.finalize("failed" if exc_type else "completed")
        return False  # never suppress exceptions

    # --- helpers ------------------------------------------------------------
    def _write_manifest(self) -> None:
        self.manifest["updated_at"] = _now()
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2), encoding="utf-8")

    @staticmethod
    def load_rounds(run_dir: str | Path) -> list[RoundRecord]:
        path = Path(run_dir) / "rounds.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [RoundRecord.model_validate_json(ln) for ln in lines if ln.strip()]
