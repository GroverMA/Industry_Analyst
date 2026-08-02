"""Universal, industry-neutral project state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.analysis import IndustryAnalysisArtifact
from src.models.enterprise import EnterpriseSensingArtifact
from src.models.evidence import EvidenceCollectionArtifact
from src.models.future import FutureIntelligenceArtifact
from src.models.report import GeneralReportArtifact
from src.models.revision import ContentRevisionArtifact
from src.models.research import ResearchBriefArtifact, ResearchPlanArtifact
from src.models.strategy import (
    ActionPlanArtifact,
    CompanyScorecardArtifact,
    EnterpriseDecisionReportArtifact,
)


class ResearchMode(StrEnum):
    GENERAL = "general_research"
    INDUSTRY_PACK = "industry_pack"
    GOLDEN_CASE = "golden_case"
    DEMO_FALLBACK = "demo_fallback"


class WorkspaceMode(StrEnum):
    QUICK_REPORT = "quick_report"
    ANALYST_WORKSPACE = "analyst_workspace"


class WorkflowStatus(StrEnum):
    NOT_STARTED = "not_started"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


WORKFLOW_STEPS: tuple[tuple[str, str, str], ...] = (
    ("research_brief", "Research Brief", "定义研究目标、市场边界与可选业务决策"),
    ("research_planning", "Research Planning", "拆解问题、假设、信息需求与校验节点"),
    (
        "evidence_collection",
        "Evidence Collection",
        "检索公开来源，并在用户提供时接收可选企业输入",
    ),
    ("evidence_qa", "Evidence QA", "检查来源、口径、时效性、冲突与缺口"),
    ("industry_analysis", "Industry Analysis", "分析现状、价值链、竞争者与驱动因素"),
    ("future_intelligence", "Future Intelligence", "形成趋势、情景、领先指标与反证条件"),
    ("company_assessment", "Company Assessment", "评价公司优势、差距、风险与战略适配"),
    ("action_plan", "Action Plan", "形成负责人、时间、指标、风险和停止条件"),
    ("human_review", "Human Review", "审核关键证据、逻辑、判断与责任边界"),
    ("decision_report", "Decision Report", "生成可追溯、可审阅、可行动的决策报告"),
)


def default_workflow() -> dict[str, WorkflowStatus]:
    return {
        key: WorkflowStatus.READY if key == "research_brief" else WorkflowStatus.NOT_STARTED
        for key, _, _ in WORKFLOW_STEPS
    }


class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: uuid4().hex)
    project_name: str
    industry: str
    region: str
    target_company: str | None = None
    company_strategy_enabled: bool = False
    company_strategy_objective: str | None = None
    decision_context: str | None = None
    research_objective: str
    time_horizon: str
    output_language: str = "简体中文"
    research_mode: ResearchMode = ResearchMode.GENERAL
    workspace_mode: WorkspaceMode = WorkspaceMode.QUICK_REPORT
    execution_authorized_at: datetime | None = None
    market_scope_confirmed_at: datetime | None = None
    last_pipeline_error: str | None = None
    industry_pack: str | None = None
    research_brief_artifact: ResearchBriefArtifact | None = None
    research_plan_artifact: ResearchPlanArtifact | None = None
    evidence_collection_artifact: EvidenceCollectionArtifact | None = None
    industry_analysis_artifact: IndustryAnalysisArtifact | None = None
    future_intelligence_artifact: FutureIntelligenceArtifact | None = None
    enterprise_sensing_artifact: EnterpriseSensingArtifact | None = None
    general_report_artifact: GeneralReportArtifact | None = None
    company_scorecard_artifact: CompanyScorecardArtifact | None = None
    action_plan_artifact: ActionPlanArtifact | None = None
    enterprise_decision_report_artifact: EnterpriseDecisionReportArtifact | None = None
    content_revision_artifact: ContentRevisionArtifact | None = None
    current_step: str = "research_brief"
    workflow_status: dict[str, WorkflowStatus] = Field(default_factory=default_workflow)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator(
        "project_name",
        "industry",
        "region",
        "research_objective",
        "time_horizon",
    )
    @classmethod
    def require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("required project fields cannot be empty")
        return cleaned

    @field_validator(
        "target_company",
        "company_strategy_objective",
        "decision_context",
        "industry_pack",
    )
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def require_company_strategy_inputs(self) -> "ProjectState":
        if self.company_strategy_enabled and not self.target_company:
            raise ValueError("company strategy path requires a target company")
        if self.company_strategy_enabled and not self.company_strategy_objective:
            raise ValueError("company strategy path requires a strategy objective")
        return self

    def update_step(self, step: str, status: WorkflowStatus) -> "ProjectState":
        if step not in self.workflow_status:
            raise ValueError(f"unknown workflow step: {step}")
        statuses = dict(self.workflow_status)
        statuses[step] = status
        return self.model_copy(
            update={
                "current_step": step,
                "workflow_status": statuses,
                "updated_at": datetime.now(UTC),
            }
        )

    @property
    def completion_ratio(self) -> float:
        applicable = [
            status
            for status in self.workflow_status.values()
            if status != WorkflowStatus.NOT_APPLICABLE
        ]
        completed = sum(
            status == WorkflowStatus.COMPLETED
            for status in applicable
        )
        return completed / len(applicable) if applicable else 0.0


def rewind_to_previous_review_gate(
    project: ProjectState,
) -> tuple[ProjectState, str] | None:
    """Return to the prior human gate while invalidating only stale outputs."""

    statuses = dict(project.workflow_status)
    strategy_reset = {
        "company_scorecard_artifact": None,
        "action_plan_artifact": None,
        "enterprise_decision_report_artifact": None,
        "content_revision_artifact": None,
    }
    if project.general_report_artifact is not None or (
        project.industry_analysis_artifact is not None
        and project.future_intelligence_artifact is not None
        and (
            project.industry_analysis_artifact.human_confirmed
            or project.future_intelligence_artifact.human_confirmed
        )
    ):
        analysis = project.industry_analysis_artifact
        future = project.future_intelligence_artifact
        statuses["industry_analysis"] = WorkflowStatus.NEEDS_REVIEW
        statuses["future_intelligence"] = WorkflowStatus.NEEDS_REVIEW
        statuses["human_review"] = WorkflowStatus.NEEDS_REVIEW
        statuses["decision_report"] = WorkflowStatus.READY
        updated = project.model_copy(
            update={
                "industry_analysis_artifact": (
                    analysis.model_copy(update={"human_confirmed": False})
                    if analysis is not None
                    else None
                ),
                "future_intelligence_artifact": (
                    future.model_copy(update={"human_confirmed": False})
                    if future is not None
                    else None
                ),
                "general_report_artifact": None,
                **strategy_reset,
                "workflow_status": statuses,
                "current_step": "human_review",
                "updated_at": datetime.now(UTC),
            }
        )
        return updated, "已返回Gate 2内容审核；报告与企业决策输出需要重新生成。"

    if project.industry_analysis_artifact is not None or (
        project.evidence_collection_artifact is not None
        and project.evidence_collection_artifact.human_confirmed
    ):
        evidence = project.evidence_collection_artifact
        statuses["evidence_collection"] = WorkflowStatus.NEEDS_REVIEW
        statuses["evidence_qa"] = WorkflowStatus.NEEDS_REVIEW
        for step in (
            "industry_analysis",
            "future_intelligence",
            "human_review",
            "decision_report",
        ):
            statuses[step] = WorkflowStatus.NOT_STARTED
        updated = project.model_copy(
            update={
                "evidence_collection_artifact": (
                    evidence.model_copy(update={"human_confirmed": False})
                    if evidence is not None
                    else None
                ),
                "industry_analysis_artifact": None,
                "future_intelligence_artifact": None,
                "general_report_artifact": None,
                **strategy_reset,
                "workflow_status": statuses,
                "current_step": "evidence_qa",
                "updated_at": datetime.now(UTC),
            }
        )
        return updated, "已返回Gate 1证据审核；后续分析、趋势和报告需要重新生成。"

    if project.research_brief_artifact is not None and (
        project.research_brief_artifact.human_confirmed
        or project.research_plan_artifact is not None
        or project.evidence_collection_artifact is not None
    ):
        brief = project.research_brief_artifact.model_copy(
            update={"human_confirmed": False}
        )
        statuses = default_workflow()
        statuses["research_brief"] = WorkflowStatus.NEEDS_REVIEW
        if not project.company_strategy_enabled:
            statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
            statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE
        updated = project.model_copy(
            update={
                "research_brief_artifact": brief,
                "research_plan_artifact": None,
                "evidence_collection_artifact": None,
                "industry_analysis_artifact": None,
                "future_intelligence_artifact": None,
                "general_report_artifact": None,
                **strategy_reset,
                "execution_authorized_at": None,
                "market_scope_confirmed_at": None,
                "workflow_status": statuses,
                "current_step": "research_brief",
                "updated_at": datetime.now(UTC),
            }
        )
        return updated, "已返回Gate 0市场口径；确认修改后需要重新执行研究。"
    return None
