from __future__ import annotations

import asyncio

import pytest

from src.models.enterprise import (
    EnterpriseEvidenceCategory,
    EnterpriseEvidenceItem,
    EnterpriseReviewStatus,
    EnterpriseSensingArtifact,
    EnterpriseStatementType,
)
from src.models.evidence import (
    EvidenceItem,
    EvidenceKind,
    EvidenceReviewStatus,
    TaskEvidenceRun,
)
from src.models.report import GeneralReportArtifact
from src.models.strategy import EnterpriseDecisionReportArtifact, StrategyReviewStatus
from src.services.reviewer_orchestration import (
    ReviewerOrchestrationService,
    ReviewerPipelineError,
)
from src.state.project import ProjectState, WorkflowStatus
from src.ui.pages.research_studio import _reference_check_items


class _Artifact:
    def __init__(self, **values) -> None:
        self.__dict__.update(values)

    def model_copy(self, *, update: dict):
        return _Artifact(**{**self.__dict__, **update})


def _project(*, enterprise: bool = False, confirmed: bool = True) -> ProjectState:
    strategy = {}
    if enterprise:
        strategy = {
            "company_strategy_enabled": True,
            "target_company": "Example Co",
            "company_strategy_objective": "选择未来三年的增长路径",
        }
    project = ProjectState(
        project_name="Reviewer report-first test",
        industry="Molecular diagnostics",
        region="China",
        research_objective="研究市场规模、竞争格局和未来趋势",
        time_horizon="2026-2030",
        **strategy,
    )
    brief = _Artifact(human_confirmed=confirmed)
    task = _Artifact(
        task_id="T01",
        title="行业定义",
        questions=["市场如何定义？"],
        prompt_question_ids=[],
    )
    plan = _Artifact(artifact_id="PLAN-1", tasks=[task])
    update = {"research_brief_artifact": brief, "research_plan_artifact": plan}
    if enterprise:
        enterprise_item = EnterpriseEvidenceItem(
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
            entries=[enterprise_item],
            consent_to_model_processing=True,
            human_confirmed=True,
        )
    return project.model_copy(update=update)


def _evidence_run() -> TaskEvidenceRun:
    item = EvidenceItem(
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
        question_ids=["T01-Q1"],
        qa_score=90,
        review_status=EvidenceReviewStatus.NEEDS_REVIEW,
    )
    return TaskEvidenceRun(
        task_id="T01",
        task_title="行业定义",
        queries_used=["China molecular diagnostics"],
        evidence=[item],
    )


class _EvidenceService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def collect_task(self, project, plan, task_id):
        self.calls.append("reference_collection")
        return _evidence_run()


class _IndustryService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def generate(self, project, evidence):
        self.calls.append("industry_analysis")
        assert evidence.human_confirmed is True
        assert evidence.evidence[0].review_status == EvidenceReviewStatus.ACCEPTED
        finding = _Artifact(
            review_status="needs_review",
            finding_id="FND-1",
        )
        module = _Artifact(findings=[finding])
        return _Artifact(
            artifact_id="ANA-1",
            evidence_collection_id=evidence.artifact_id,
            modules=[module],
            company_implications=[],
        )


class _FutureService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def generate(self, project, evidence, analysis, *, allow_pending_findings=False):
        self.calls.append("future_intelligence")
        assert allow_pending_findings is True
        return _Artifact(
            artifact_id="FUT-1",
            industry_analysis_id=analysis.artifact_id,
            evidence_collection_id=evidence.artifact_id,
            trends=[_Artifact(review_status="needs_review", trend_id="TRD-1")],
            scenarios=[_Artifact(review_status="needs_review", scenario_id="SCN-1")],
        )


class _ReportService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def generate(self, project):
        self.calls.append("general_report")
        assert project.evidence_collection_artifact.human_confirmed is True
        assert project.industry_analysis_artifact.human_confirmed is True
        assert project.future_intelligence_artifact.human_confirmed is True
        return GeneralReportArtifact(
            title="Industry report",
            markdown="# Industry report",
            accepted_evidence_ids=["EVD-1"],
        )


class _CompanyService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def generate(self, project):
        self.calls.append("company_scorecard")
        dimensions = [
            _Artifact(
                score=80,
                weight=0.2,
                review_status=StrategyReviewStatus.NEEDS_REVIEW,
            )
            for _ in range(3)
        ]
        return _Artifact(artifact_id="SCR-1", dimensions=dimensions)


class _ActionService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def generate(self, project):
        self.calls.append("action_plan")
        assert project.company_scorecard_artifact.human_confirmed is True
        return _Artifact(
            artifact_id="APL-1",
            scorecard_id="SCR-1",
            actions=[_Artifact(review_status=StrategyReviewStatus.NEEDS_REVIEW)],
        )


def _service(calls: list[str], *, enterprise: bool) -> ReviewerOrchestrationService:
    def _enterprise_report(project):
        calls.append("enterprise_report")
        assert project.action_plan_artifact.human_confirmed is True
        return EnterpriseDecisionReportArtifact(
            title="Enterprise report",
            general_report_id=project.general_report_artifact.report_id,
            scorecard_id="SCR-1",
            action_plan_id="APL-1",
            markdown="# Enterprise report",
        )

    return ReviewerOrchestrationService(
        planning=_Artifact(),
        evidence=_EvidenceService(calls),
        industry=_IndustryService(calls),
        future=_FutureService(calls),
        report=_ReportService(calls),
        company=_CompanyService(calls) if enterprise else None,
        action=_ActionService(calls) if enterprise else None,
        enterprise_report_builder=_enterprise_report,
    )


def test_general_reviewer_orchestration_generates_report_before_trace_review() -> None:
    calls: list[str] = []

    result = asyncio.run(_service(calls, enterprise=False).run(_project()))

    assert calls == [
        "reference_collection",
        "industry_analysis",
        "future_intelligence",
        "general_report",
    ]
    assert result.enterprise is False
    assert result.report.report_status == "reviewer_draft"
    assert result.project.current_step == "decision_report"
    assert result.project.workflow_status["evidence_qa"] == WorkflowStatus.NEEDS_REVIEW
    # Persisted artifacts remain pending; the accepted IDs in the report define
    # the Reference Check set until the human reviewer confirms them.
    assert result.project.evidence_collection_artifact.evidence[0].review_status == EvidenceReviewStatus.NEEDS_REVIEW
    assert result.project.general_report_artifact.accepted_evidence_ids == ["EVD-1"]
    reference_items = _reference_check_items(result.project)
    assert [item.evidence_id for item in reference_items] == ["EVD-1"]


def test_enterprise_reviewer_orchestration_generates_scorecard_action_and_report() -> None:
    calls: list[str] = []

    result = asyncio.run(
        _service(calls, enterprise=True).run(_project(enterprise=True))
    )

    assert calls == [
        "reference_collection",
        "industry_analysis",
        "future_intelligence",
        "general_report",
        "company_scorecard",
        "action_plan",
        "enterprise_report",
    ]
    assert result.enterprise is True
    assert result.project.general_report_artifact is not None
    assert result.project.company_scorecard_artifact is not None
    assert result.project.action_plan_artifact is not None
    assert result.project.enterprise_decision_report_artifact is not None
    assert result.report.title == "Enterprise report"


def test_enterprise_reviewer_requires_confirmed_company_inputs() -> None:
    calls: list[str] = []
    project = _project(enterprise=True).model_copy(
        update={"enterprise_sensing_artifact": None}
    )

    with pytest.raises(ReviewerPipelineError, match="企业一手资料"):
        asyncio.run(_service(calls, enterprise=True).run(project))

    assert calls == []
