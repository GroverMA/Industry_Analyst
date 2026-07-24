"""Golden Case loader kept separate from the universal Research Core."""

from __future__ import annotations

import json
from pathlib import Path

from src.state.project import ProjectState


DEFAULT_GOLDEN_CASE_PATH = (
    Path(__file__).resolve().parents[2] / "demo_data" / "golden_case_project.json"
)


def load_golden_case(path: Path = DEFAULT_GOLDEN_CASE_PATH) -> ProjectState:
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    return ProjectState.model_validate(payload)

