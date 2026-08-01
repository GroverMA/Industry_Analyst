from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from src.models.enterprise import (
    EnterpriseEvidenceCategory,
    EnterpriseEvidenceItem,
    EnterpriseReviewStatus,
    EnterpriseSensingArtifact,
    EnterpriseStatementType,
)
from src.models.evidence import (
    EvidenceCollectionArtifact,
    EvidenceItem,
    EvidenceKind,
    EvidenceReviewStatus,
    TaskEvidenceRun,
)
from src.models.report import GeneralReportArtifact
from src.models.strategy import EnterpriseDecisionReportArtifact
from src.state.project import ProjectState
from src.state.user_role import (
    USER_ROLE_KEY,
    UserRole,
    get_user_role,
    set_user_role,
)
from src.ui.pages import research_studio


@dataclass
class _Copyable:
    findings: list = None
    trends: list = None
    scenarios: list = None
    dimensions: list = None
    actions: list = None
    human_confirmed: bool = False
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.findings = self.findings or []
        self.trends = self.trends or []
        self.scenarios = self.scenarios or []
        self.dimensions = self.dimensions or []
        self.actions = self.actions or []

    def model_copy(self, *, update: dict):
        return replace(self, **update)


class _Progress:
    def __init__(self) -> None:
        self.updates: list[tuple[float, str | None]] = []
        self.emptied = False

    def progress(self, value: float, *, text: str | None = None) -> None:
        self.updates.append((value, text))

    def empty(self) -> None:
        self.emptied = True


class _StreamlitStub:
    def __init__(self) -> None:
        self.progress_bar = _Progress()
        self.errors: list[str] = []
        self.rerun_called = False

    def progress(self, value: float, *, text: str | None = None) -> _Progress:
        self.progress_bar.updates.append((value, text))
        return self.progress_bar

    def error(self, message: str) -> None:
        self.errors.append(message)

    def rerun(self) -> None:
        self.rerun_called = True


class _Service:
    def __init__(self, value, calls: list[str], name: str) -> None:
        self.value = value
        self.calls = calls
        self.name = name

    def generate(self, *args):
        self.calls.append(self.name)
        return self.value


def _project(*, enterprise: bool) -> ProjectState:
    kwargs = {}
    if enterprise:
        kwargs = {
            "company_strategy_enabled": True,
            "target_company": "Example Co",
            "company_strategy_objective": "选择未来三年的增长路径",
        }
    project = ProjectState(
        project_name="Reviewer flow",
        industry="Molecular diagnostics",
        region="China",
        research_objective="研究市场规模、竞争格局和未来趋势",
        time_horizon="2026-2030",
        **kwargs,
    )
    brief = _Copyable(human_confirmed=True)
    plan = type("Plan", (), {"artifact_id": "PLAN-1", "tasks": []})()
    evidence = EvidenceItem(
        evidence_id="EVD-1",
        task_id="T01",
        source_id="SRC-1",
        kind=EvidenceKind.FACT,
        statement="市场仍在增长。",
        supporting_excerpt="公开资料显示市场仍在增长。",
        geographic_scope="China",
        market_scope="Molecular diagnostics",
        supports_or_challenges="supports",
        model_confidence=0.9,
        prompt_relevance=0.9,
        qa_score=90,
        review_status=EvidenceReviewStatus.NEEDS_REVIEW,
    )
    run = TaskEvidenceRun(
        task_id="T01",
        task_title="市场概览",
        queries_used=["China molecular diagnostics"],
        evidence=[evidence],
    )
    collection = EvidenceCollectionArtifact(
        research_plan_id="PLAN-1",
        task_runs=[run],
    )
    update = {
        "research_brief_artifact": brief,
        "research_plan_artifact": plan,
        "evidence_collection_artifact": collection,
    }
    if enterprise:
        entry = EnterpriseEvidenceItem(
            title="渠道复盘",
            category=EnterpriseEvidenceCategory.SALES_CHANNEL,
            statement_type=EnterpriseStatementType.FACT,
            content="重点区域渠道覆盖率仍有提升空间。",
            source_owner="销售负责人",
            strategic_relevance="用于判断增长路径可执行性。",
            review_status=EnterpriseReviewStatus.ACCEPTED,
        )
        update["enterprise_sensing_artifact"] = EnterpriseSensingArtifact(
            project_id=project.project_id,
            target_company_snapshot=project.target_company,
            strategy_objective_snapshot=project.company_strategy_objective,
            entries=[entry],
            consent_to_model_processing=True,
            human_confirmed=True,
        )
    return project.model_copy(update=update)


def _install_reviewer_pipeline_fakes(monkeypatch, project: ProjectState, *, enterprise: bool):
    calls: list[str] = []
    saves: list[ProjectState] = []
    st = _StreamlitStub()
    general_report = GeneralReportArtifact(title="Industry report", markdown="# Report")
    update = {"general_report_artifact": general_report, "current_step": "decision_report"}
    if enterprise:
        update.update(
            {
                "company_scorecard_artifact": _Copyable(),
                "action_plan_artifact": _Copyable(),
                "enterprise_decision_report_artifact": EnterpriseDecisionReportArtifact(
                    title="Enterprise report",
                    general_report_id=general_report.report_id,
                    scorecard_id="SCR-1",
                    action_plan_id="APL-1",
                    markdown="# Enterprise report",
                ),
            }
        )
    generated_project = project.model_copy(update=update)

    class _ReviewerService:
        async def run(self, value, *, enterprise, on_progress):
            calls.append("enterprise" if enterprise else "general")
            assert value.project_id == project.project_id
            on_progress("general_report", 5, 8 if enterprise else 5)
            return SimpleNamespace(project=generated_project, warnings=())

    monkeypatch.setattr(research_studio, "st", st)
    monkeypatch.setattr(research_studio, "_save", saves.append)
    monkeypatch.setattr(
        research_studio, "reviewer_orchestration_service", lambda: _ReviewerService()
    )
    return calls, saves, st


def test_role_selection_persists_both_supported_roles() -> None:
    state: dict = {}
    assert get_user_role(state) is None
    set_user_role(state, UserRole.CONSULTANT)
    assert state[USER_ROLE_KEY] == "consultant"
    assert get_user_role(state) is UserRole.CONSULTANT
    set_user_role(state, UserRole.REVIEWER)
    assert get_user_role(state) is UserRole.REVIEWER


def test_role_selection_ui_exposes_author_and_reviewer_choices() -> None:
    def _role_app() -> None:
        from src.ui.role_selection import render_role_selection

        render_role_selection()

    app = AppTest.from_function(_role_app).run(timeout=10)

    assert not app.exception
    labels = {button.label for button in app.button}
    assert "以研究顾问身份进入" in labels
    assert "以报告审阅者身份进入" in labels


def test_reviewer_general_report_first_pipeline_generates_report_and_trace(monkeypatch) -> None:
    project = _project(enterprise=False)
    calls, saves, st = _install_reviewer_pipeline_fakes(
        monkeypatch, project, enterprise=False
    )

    research_studio._run_reviewer_report_pipeline(project)

    assert calls == ["general"]
    assert not st.errors
    assert st.rerun_called
    assert saves[-1].general_report_artifact is not None
    assert saves[-1].enterprise_decision_report_artifact is None
    assert saves[-1].current_step == "decision_report"


def test_reviewer_enterprise_report_first_pipeline_includes_strategy_outputs(monkeypatch) -> None:
    project = _project(enterprise=True)
    calls, saves, st = _install_reviewer_pipeline_fakes(
        monkeypatch, project, enterprise=True
    )

    research_studio._run_reviewer_report_pipeline(project)

    assert calls == ["enterprise"]
    assert not st.errors
    assert st.rerun_called
    assert saves[-1].general_report_artifact is not None
    assert saves[-1].company_scorecard_artifact is not None
    assert saves[-1].action_plan_artifact is not None
    assert saves[-1].enterprise_decision_report_artifact is not None


def test_reviewer_progress_places_report_before_trace_workpapers(monkeypatch) -> None:
    project = _project(enterprise=False)
    monkeypatch.setattr(research_studio, "get_user_role", lambda _state: UserRole.REVIEWER)
    monkeypatch.setattr(research_studio.st, "session_state", {})

    labels = [label for label, _ in research_studio._pipeline_flags(project)]

    assert labels == [
        "Prompt Analysis",
        "Gate 0 · Scope",
        "General Report",
        "Reference Check",
        "Industry Analysis",
        "Future Intelligence",
    ]


def test_enterprise_reviewer_progress_places_report_before_strategy_trace(monkeypatch) -> None:
    project = _project(enterprise=True)
    monkeypatch.setattr(research_studio, "get_user_role", lambda _state: UserRole.REVIEWER)
    monkeypatch.setattr(research_studio.st, "session_state", {})

    labels = [label for label, _ in research_studio._pipeline_flags(project)]

    assert labels == [
        "Enterprise Sensing",
        "Prompt Analysis",
        "Gate 0 · Scope",
        "Enterprise Report",
        "Reference Check",
        "Industry Analysis",
        "Future Intelligence",
        "Company Scorecard",
        "Action Plan",
    ]
