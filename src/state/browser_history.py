"""Browser-local project history bridge and catalog helpers.

The deployed Streamlit server is shared and its filesystem is ephemeral.  Full
project snapshots therefore live in IndexedDB in the user's browser.  Python
only receives the catalog needed by the sidebar, plus a full snapshot when the
user explicitly opens one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit.components.v1 as components

from src.state.project import ProjectState, WORKFLOW_STEPS, WorkflowStatus


HISTORY_CATALOG_KEY = "industry_analyst_history_catalog"
HISTORY_COMMAND_KEY = "industry_analyst_history_command"
HISTORY_RESPONSE_KEY = "industry_analyst_history_response"

_COMPONENT_PATH = Path(__file__).with_name("browser_history_component")
_history_component = components.declare_component(
    "industry_analyst_browser_history",
    path=str(_COMPONENT_PATH),
)

STEP_LABELS = {key: label for key, label, _ in WORKFLOW_STEPS}
VALID_HISTORY_PAGES = {
    "home",
    "research_studio",
    "research_brief",
    "workflow",
    "enterprise_sensing",
    "evidence_analysis",
    "trend_forecast",
    "company_scorecard",
    "action_plan",
    "decision_report",
}


def project_progress(project: ProjectState) -> int:
    """Return a stable whole-number progress percentage for navigation."""

    return max(0, min(100, round(project.completion_ratio * 100)))


def project_is_complete(project: ProjectState) -> bool:
    """Treat strategy-enabled work as complete only after its decision report."""

    if project.general_report_artifact is None:
        return False
    if project.company_strategy_enabled:
        return project.enterprise_decision_report_artifact is not None
    return True


def project_node_label(project: ProjectState) -> str:
    if project_is_complete(project):
        return "报告已完成"
    status = project.workflow_status.get(project.current_step)
    label = STEP_LABELS.get(project.current_step, project.current_step.replace("_", " ").title())
    if status == WorkflowStatus.NEEDS_REVIEW:
        return f"{label} · 待审核"
    if status == WorkflowStatus.BLOCKED:
        return f"{label} · 待处理"
    return label


def build_project_record(project: ProjectState, active_page: str) -> dict[str, Any]:
    """Serialize the complete resumable project plus lightweight sidebar data."""

    page = active_page if active_page in VALID_HISTORY_PAGES else "research_studio"
    return {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "industry": project.industry,
        "region": project.region,
        "progress": project_progress(project),
        "current_step": project.current_step,
        "node_label": project_node_label(project),
        "status_group": "completed" if project_is_complete(project) else "in_progress",
        "updated_at": project.updated_at.isoformat(),
        "active_page": page,
        "project_state": project.model_dump(mode="json"),
    }


def resume_page_for_project(
    project: ProjectState,
    saved_page: str | None = None,
) -> str:
    """Return the latest useful workspace page for a restored project."""

    if saved_page in VALID_HISTORY_PAGES and saved_page != "home":
        return saved_page
    if project.current_step == "company_assessment":
        return "company_scorecard"
    if project.current_step == "action_plan":
        return "action_plan"
    if project.current_step == "decision_report" and project.company_strategy_enabled:
        return "decision_report"
    return "research_studio"


def queue_history_command(state, command_type: str, **payload: Any) -> None:
    """Queue one browser-history operation for the next Streamlit rerun."""

    state[HISTORY_COMMAND_KEY] = {
        "type": command_type,
        "request_id": uuid4().hex,
        **payload,
    }


def render_history_bridge(
    *,
    project: ProjectState | None,
    active_page: str,
    command: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Render the invisible IndexedDB component and return its latest response."""

    record = build_project_record(project, active_page) if project is not None else None
    value = _history_component(
        project_record=record,
        command=command,
        key="industry_analyst_browser_history_bridge",
        default=None,
    )
    return value if isinstance(value, dict) else None


def normalize_catalog(value: Any) -> dict[str, list[dict[str, Any]]]:
    """Defensively normalize untrusted data returned by the browser component."""

    if not isinstance(value, dict):
        return {"projects": [], "folders": []}
    projects = value.get("projects")
    folders = value.get("folders")
    return {
        "projects": [item for item in projects if isinstance(item, dict)]
        if isinstance(projects, list)
        else [],
        "folders": [item for item in folders if isinstance(item, dict)]
        if isinstance(folders, list)
        else [],
    }
