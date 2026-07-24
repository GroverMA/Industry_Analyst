"""Small adapter around Streamlit's mapping-like session state."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from src.state.project import ProjectState


PROJECT_KEY = "industry_analyst_project"
ACTIVE_PAGE_KEY = "industry_analyst_active_page"


def get_project(state: MutableMapping[str, Any]) -> ProjectState | None:
    value = state.get(PROJECT_KEY)
    if value is None:
        return None
    if isinstance(value, ProjectState):
        return value
    # Streamlit hot-reload can leave an instance of the previous ProjectState
    # class in session memory. Convert any Pydantic-like value back to plain
    # data before validating it against the current class definition.
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    project = ProjectState.model_validate(value)
    state[PROJECT_KEY] = project.model_dump(mode="json")
    return project


def set_project(state: MutableMapping[str, Any], project: ProjectState) -> None:
    state[PROJECT_KEY] = project.model_dump(mode="json")


def clear_project(state: MutableMapping[str, Any]) -> None:
    state.pop(PROJECT_KEY, None)
    state[ACTIVE_PAGE_KEY] = "home"


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault(ACTIVE_PAGE_KEY, "home")
