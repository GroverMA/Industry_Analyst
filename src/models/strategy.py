"""Evidence-linked company scorecard, action plan, and strategy report models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.models.research import MethodologyTrace


class StrategyReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class BenchmarkType(StrEnum):
    DIRECT_PEER = "direct_peer"
    BEST_IN_CLASS = "best_in_class"
    STRATEGIC_THRESHOLD = "strategic_threshold"


class BenchmarkReference(BaseModel):
    benchmark_id: str = Field(default_factory=lambda: f"BMK-{uuid4().hex[:10]}")
    name: str
    benchmark_type: BenchmarkType
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)


class ScoreComponents(BaseModel):
    current_capability: int = Field(ge=0, le=5)
    benchmark_position: int = Field(ge=0, le=5)
    strategic_fit: int = Field(ge=0, le=5)
    future_readiness: int = Field(ge=0, le=5)


class CompanyScoreDimension(BaseModel):
    dimension_id: str
    title: str
    weight: float = Field(gt=0, le=1)
    score_components: ScoreComponents | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    benchmark_score: float | None = Field(default=None, ge=0, le=100)
    benchmark_gap: float | None = Field(default=None, ge=-100, le=100)
    strategic_target_score: float | None = Field(default=None, ge=0, le=100)
    strategic_target_gap: float | None = Field(default=None, ge=-100, le=100)
    core_metrics: list[str] = Field(default_factory=list)
    market_position_label: str = ""
    score_rationale: str
    benchmark_ids: list[str] = Field(default_factory=list)
    external_evidence_ids: list[str] = Field(default_factory=list)
    enterprise_evidence_ids: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    industry_relevance: str = ""
    current_market_position: str = ""
    target_position: str = ""
    strategic_gap: str = ""
    linked_trend_ids: list[str] = Field(default_factory=list)
    strategic_fit_explanation: str
    data_completeness: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    uncertainty: str
    unscored_reason: str | None = None
    review_status: StrategyReviewStatus = StrategyReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def require_traceability_for_scored_dimension(self) -> "CompanyScoreDimension":
        if self.score is None:
            if not self.unscored_reason:
                raise ValueError("unscored dimension requires a reason")
            return self
        if self.score_components is None:
            raise ValueError("scored dimension requires score components")
        if not self.external_evidence_ids or not self.enterprise_evidence_ids:
            raise ValueError("scored dimension requires external and enterprise evidence")
        if not self.benchmark_ids:
            raise ValueError("scored dimension requires an explicit benchmark")
        return self


class CompanyScorecardArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"SCR-{uuid4().hex[:10]}")
    project_id: str
    target_company_snapshot: str
    strategy_objective_snapshot: str
    industry_analysis_id: str
    future_intelligence_id: str
    enterprise_sensing_id: str
    benchmarks: list[BenchmarkReference] = Field(min_length=1)
    dimensions: list[CompanyScoreDimension] = Field(min_length=4, max_length=8)
    weighted_score: float | None = Field(default=None, ge=0, le=100)
    weighted_benchmark_score: float | None = Field(default=None, ge=0, le=100)
    weighted_gap: float | None = Field(default=None, ge=-100, le=100)
    weighted_strategic_target_score: float | None = Field(default=None, ge=0, le=100)
    weighted_strategic_target_gap: float | None = Field(default=None, ge=-100, le=100)
    scored_weight: float = Field(ge=0, le=1)
    overall_assessment: str
    strategic_advantages: list[str] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    cross_dimension_risks: list[str] = Field(default_factory=list)
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
    confirmed_at: datetime | None = None


class ActionPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KPIType(StrEnum):
    LEADING = "leading"
    OUTCOME = "outcome"


class ActionKPI(BaseModel):
    name: str
    kpi_type: KPIType
    definition: str
    target: str
    timing: str
    data_source: str


class StrategicAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"ACT-{uuid4().hex[:10]}")
    title: str
    rationale: str
    strategic_objective: str
    priority: ActionPriority
    owner_role: str
    timing: str
    resources: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    kpis: list[ActionKPI] = Field(min_length=2)
    risks: list[str] = Field(min_length=1)
    mitigations: list[str] = Field(min_length=1)
    stop_conditions: list[str] = Field(min_length=1)
    score_dimension_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    enterprise_evidence_ids: list[str] = Field(min_length=1)
    trend_ids: list[str] = Field(min_length=1)
    scenario_ids: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    uncertainty: str
    review_status: StrategyReviewStatus = StrategyReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def require_leading_and_outcome_kpis(self) -> "StrategicAction":
        kinds = {item.kpi_type for item in self.kpis}
        if KPIType.LEADING not in kinds or KPIType.OUTCOME not in kinds:
            raise ValueError("action requires leading and outcome KPIs")
        return self


class ActionPlanArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"APL-{uuid4().hex[:10]}")
    project_id: str
    target_company_snapshot: str
    strategy_objective_snapshot: str
    scorecard_id: str
    actions: list[StrategicAction] = Field(min_length=3, max_length=10)
    sequencing_logic: list[str] = Field(min_length=1)
    rejected_options: list[str] = Field(default_factory=list)
    portfolio_risks: list[str] = Field(default_factory=list)
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
    confirmed_at: datetime | None = None


class EnterpriseDecisionReportArtifact(BaseModel):
    report_id: str = Field(default_factory=lambda: f"EDR-{uuid4().hex[:10]}")
    title: str
    general_report_id: str
    scorecard_id: str
    action_plan_id: str
    markdown: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
