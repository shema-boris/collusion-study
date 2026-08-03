"""Config loading. Nothing operational is hardcoded in source (DESIGN.md §10)."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
