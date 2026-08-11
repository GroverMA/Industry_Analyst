"""Evidence-linked company scorecard, action plan, and strategy report models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.models.research import MethodologyTrace


# A capability index is not a percentile or an ideal-state score.  These
# dimension anchors represent the observable average capability of comparable
# market players on a 0-100 scale.  The assessment service may refine them
# from evidence, but legacy 90-point "benchmarks" must not be treated as an
# actual market average.
MARKET_AVERAGE_BY_DIMENSION: dict[str, float] = {
    "market_position": 58.0,
    "product_competitiveness": 62.0,
    "commercialization_channel": 57.0,
    "operations_economics": 60.0,
    "innovation_future_fit": 54.0,
    "organization_execution": 56.0,
    "regulatory_localization": 59.0,
    "digital_data": 52.0,
}


STRATEGY_DIMENSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market_position": ("市场", "份额", "进入", "定位", "竞争"),
    "product_competitiveness": ("产品", "产品线", "组合", "创新", "差异化"),
    "commercialization_channel": ("客户", "医院", "渠道", "销售", "渗透", "覆盖"),
    "operations_economics": ("利润", "成本", "库存", "交付", "效率", "运营"),
    "innovation_future_fit": ("未来", "研发", "技术", "新品", "趋势"),
    "organization_execution": ("组织", "资源", "执行", "团队", "协同"),
    "regulatory_localization": ("本地化", "国产化", "供应链", "监管", "合规", "准入"),
    "digital_data": ("数字化", "数据", "AI", "人工智能", "软件", "智能化"),
}


def normalized_market_average(dimension_id: str, value: float | None) -> float:
    """Return an actual-market average, replacing legacy ideal-state values."""

    fallback = MARKET_AVERAGE_BY_DIMENSION.get(dimension_id, 57.0)
    try:
        score = float(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback
    # Below 35 is normally a distressed-tail observation and above 78 is
    # normally best-in-class/target state, neither of which is a market mean.
    if score < 35 or score > 78:
        return fallback
    return round(score, 1)


def derived_strategic_target(
    dimension_id: str,
    benchmark_score: float,
    strategy_objective: str,
    components: "ScoreComponents | None" = None,
) -> float:
    """Derive the capability threshold required by the stated strategy."""

    objective = str(strategy_objective or "").lower()
    keywords = STRATEGY_DIMENSION_KEYWORDS.get(dimension_id, ())
    strategic_emphasis = any(keyword.lower() in objective for keyword in keywords)
    uplift = 12.0 + (7.0 if strategic_emphasis else 0.0)
    if components is not None:
        uplift += max(0, components.strategic_fit - 3) * 2.0
        uplift += max(0, components.future_readiness - 3) * 1.5
    return round(min(95.0, benchmark_score + uplift), 1)


def market_position_from_gap(company_score: float, benchmark_score: float) -> str:
    delta = company_score - benchmark_score
    if delta >= 10:
        return "领先市场平均水平"
    if delta >= -5:
        return "达到或接近市场平均水平"
    if delta >= -20:
        return "低于市场平均水平，处于追赶位置"
    return "显著低于市场平均水平"


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

    @model_validator(mode="after")
    def upgrade_comparison_scores(self) -> "CompanyScorecardArtifact":
        """Upgrade saved scorecards to the three-series comparison contract.

        Browser-persisted projects can survive several deployments.  Older
        artifacts stored an ideal 90-point threshold as the market benchmark
        and had no strategic-target fields.  Recomputing here makes both the
        build-first and review-first workspaces render the same complete radar
        without asking the user to repeat research.
        """

        dimensions: list[CompanyScoreDimension] = []
        for item in self.dimensions:
            benchmark = normalized_market_average(item.dimension_id, item.benchmark_score)
            target = item.strategic_target_score
            if target is None or target < benchmark or target > 98:
                target = derived_strategic_target(
                    item.dimension_id,
                    benchmark,
                    self.strategy_objective_snapshot,
                    item.score_components,
                )
            score = item.score
            dimensions.append(
                item.model_copy(
                    update={
                        "benchmark_score": benchmark,
                        "benchmark_gap": (
                            round(benchmark - score, 1) if score is not None else None
                        ),
                        "strategic_target_score": target,
                        "strategic_target_gap": (
                            round(target - score, 1) if score is not None else None
                        ),
                        "market_position_label": (
                            market_position_from_gap(score, benchmark)
                            if score is not None
                            else item.market_position_label
                        ),
                    }
                )
            )

        scored = [item for item in dimensions if item.score is not None]
        scored_weight = round(sum(item.weight for item in scored), 4)
        if scored_weight:
            weighted_score = round(
                sum(float(item.score) * item.weight for item in scored) / scored_weight,
                1,
            )
            weighted_benchmark = round(
                sum(float(item.benchmark_score) * item.weight for item in scored)
                / scored_weight,
                1,
            )
            weighted_target = round(
                sum(float(item.strategic_target_score) * item.weight for item in scored)
                / scored_weight,
                1,
            )
        else:
            weighted_score = None
            weighted_benchmark = None
            weighted_target = None
        # Mutate the validated instance instead of returning a copied model.
        # Pydantic's ``__init__`` path ignores replacement instances returned
        # by an ``after`` validator, which previously left new scorecards in
        # the legacy two-series state until they were reloaded.
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "weighted_score", weighted_score)
        object.__setattr__(self, "weighted_benchmark_score", weighted_benchmark)
        object.__setattr__(
            self,
            "weighted_gap",
            (
                round(weighted_benchmark - weighted_score, 1)
                if weighted_benchmark is not None and weighted_score is not None
                else None
            ),
        )
        object.__setattr__(self, "weighted_strategic_target_score", weighted_target)
        object.__setattr__(
            self,
            "weighted_strategic_target_gap",
            (
                round(weighted_target - weighted_score, 1)
                if weighted_target is not None and weighted_score is not None
                else None
            ),
        )
        object.__setattr__(self, "scored_weight", scored_weight)
        return self


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
