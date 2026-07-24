from __future__ import annotations

from pydantic import ValidationError

from src.state.project import ProjectState, ResearchMode, WorkflowStatus, WorkspaceMode
from src.state.session import PROJECT_KEY, clear_project, get_project, set_project


def make_project() -> ProjectState:
    return ProjectState(
        project_name="Global Robotics Study",
        industry="Industrial Robotics",
        region="Global",
        target_company=None,
        decision_context="Choose a market entry strategy",
        research_objective="Assess competitors, drivers, and future trends",
        time_horizon="2026-2030",
    )


def test_general_project_is_industry_neutral() -> None:
    project = make_project()

    assert project.industry == "Industrial Robotics"
    assert project.research_mode == ResearchMode.GENERAL
    assert project.industry_pack is None
    assert project.workflow_status["research_brief"] == WorkflowStatus.READY
    assert project.completion_ratio == 0


def test_project_rejects_blank_required_fields() -> None:
    try:
        ProjectState(
            project_name=" ",
            industry="Software",
            region="Global",
            decision_context="Decide",
            research_objective="Research",
            time_horizon="2026",
        )
    except ValidationError:
        return
    raise AssertionError("blank project name should fail validation")


def test_project_allows_exploratory_research_without_business_decision() -> None:
    project = ProjectState(
        project_name="Industry Landscape",
        industry="Industrial Robotics",
        region="Global",
        research_objective="Understand the industry, competitors, and trends",
        time_horizon="2026-2030",
    )

    assert project.decision_context is None


def test_company_strategy_path_requires_target_company_and_strategy_objective() -> None:
    try:
        ProjectState(
            project_name="Company Strategy",
            industry="Diagnostics",
            region="China",
            company_strategy_enabled=True,
            research_objective="Assess the market",
            time_horizon="2026-2030",
        )
    except ValidationError:
        return
    raise AssertionError("company strategy path should require company and objective")


def test_company_strategy_path_accepts_explicit_strategic_intent() -> None:
    project = ProjectState(
        project_name="Company Strategy",
        industry="Diagnostics",
        region="China",
        target_company="Demo Diagnostics",
        company_strategy_enabled=True,
        company_strategy_objective="Protect the core business while entering digital PCR",
        research_objective="Assess the market",
        time_horizon="2026-2030",
    )

    assert project.company_strategy_enabled is True
    assert project.company_strategy_objective.startswith("Protect")


def test_not_applicable_steps_are_excluded_from_completion_ratio() -> None:
    project = make_project()
    statuses = dict(project.workflow_status)
    statuses["research_brief"] = WorkflowStatus.COMPLETED
    statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
    statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE

    updated = project.model_copy(update={"workflow_status": statuses})

    assert updated.completion_ratio == 1 / 8


def test_project_snapshot_preserves_workspace_mode() -> None:
    project = make_project().model_copy(
        update={"workspace_mode": WorkspaceMode.ANALYST_WORKSPACE}
    )

    restored = ProjectState.model_validate_json(project.model_dump_json())

    assert restored == project
    assert restored.workspace_mode == WorkspaceMode.ANALYST_WORKSPACE


def test_workflow_status_update_is_immutable() -> None:
    project = make_project()

    updated = project.update_step("research_brief", WorkflowStatus.COMPLETED)

    assert project.workflow_status["research_brief"] == WorkflowStatus.READY
    assert updated.workflow_status["research_brief"] == WorkflowStatus.COMPLETED


def test_session_helpers_round_trip_project() -> None:
    state: dict = {}
    project = make_project()

    set_project(state, project)
    assert isinstance(state[PROJECT_KEY], dict)
    assert get_project(state) == project
    clear_project(state)
    assert get_project(state) is None
