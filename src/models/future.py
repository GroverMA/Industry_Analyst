"""Evidence-linked future intelligence and scenario artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.research import MethodologyTrace


class ForecastReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TrendCategory(StrEnum):
    TECHNOLOGY_PRODUCT = "technology_product"
    COMPETITIVE_LANDSCAPE = "competitive_landscape"
    BUSINESS_MODEL = "business_model"
    CUSTOMER_DEMAND = "customer_demand"
    POLICY_CAPITAL_VALUE_CHAIN = "policy_capital_value_chain"
    CROSS_CUTTING = "cross_cutting"


class PlayerMoveStatus(StrEnum):
    OBSERVED = "observed"
    ANNOUNCED = "announced"
    INFERRED = "inferred"


class ScenarioType(StrEnum):
    BASELINE = "baseline"
    ACCELERATED = "accelerated"
    BLOCKED = "blocked"


class ForecastMethod(StrEnum):
    CAUSAL_SCENARIO = "causal_scenario"
    NAIVE_BASELINE = "naive_baseline"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    TREND_REGRESSION = "trend_regression"
    REGULARIZED_DRIVER_REGRESSION = "regularized_driver_regression"


class ForecastMethodology(BaseModel):
    """Auditable quantitative-method gate for Future Intelligence."""

    data_sufficiency: str
    structured_observation_count: int = Field(ge=0)
    selected_method: ForecastMethod
    benchmark_method: ForecastMethod
    candidate_methods: list[ForecastMethod] = Field(min_length=1)
    validation_design: str
    error_metrics: list[str] = Field(min_length=1)
    prediction_interval: str
    quantitative_forecast_used: bool
    selection_rationale: str
    model_limitations: list[str] = Field(min_length=1)


class ObservedSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: f"SIG-{uuid4().hex[:10]}")
    signal_type: str
    description: str
    actor: str | None = None
    signal_date: str | None = None
    evidence_ids: list[str] = Field(min_length=1)
    finding_ids: list[str] = Field(default_factory=list)
    direction: str


class PlayerMove(BaseModel):
    player: str
    move_status: PlayerMoveStatus
    current_signal: str
    inferred_next_move: str
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)
    uncertainty: str


class LeadingIndicator(BaseModel):
    name: str
    definition: str
    direction_to_watch: str
    trigger_condition: str
    data_source: str
    monitoring_frequency: str


class ForecastConfidence(BaseModel):
    evidence_quality: int = Field(ge=0, le=100)
    source_diversity: int = Field(ge=0, le=100)
    signal_consistency: int = Field(ge=0, le=100)
    causal_clarity: int = Field(ge=0, le=100)
    player_commitment: int = Field(ge=0, le=100)
    time_distance: int = Field(ge=0, le=100)
    counter_evidence_resilience: int = Field(ge=0, le=100)
    enterprise_signal_support: int | None = Field(default=None, ge=0, le=100)
    overall: int = Field(ge=0, le=100)


class FutureTrend(BaseModel):
    trend_id: str = Field(default_factory=lambda: f"TRD-{uuid4().hex[:10]}")
    title: str
    category: TrendCategory
    forecast_horizon: str
    forecast_year_end: int
    forecast_statement: str
    observed_signals: list[ObservedSignal] = Field(min_length=1)
    causal_mechanism: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    affected_players: list[str] = Field(min_length=1)
    player_moves: list[PlayerMove] = Field(default_factory=list)
    competition_impact: str
    business_model_impact: str
    customer_demand_impact: str
    company_exposure: str | None = None
    leading_indicators: list[LeadingIndicator] = Field(min_length=1)
    falsification_conditions: list[str] = Field(min_length=1)
    uncertainties: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    finding_ids: list[str] = Field(min_length=1)
    counter_evidence_ids: list[str] = Field(default_factory=list)
    confidence: ForecastConfidence
    confidence_note: str
    core_trend: str = ""
    target_industry_metric: str = ""
    factor_class: str = "structural"
    temporal_role: str = "future_opportunity"
    direct_variables: list[str] = Field(default_factory=list)
    verification_metrics: list[str] = Field(default_factory=list)
    positive_effect: str = ""
    negative_effect: str = ""
    dynamic_supply_demand_feedback: str = ""
    net_impact_summary: str = ""
    market_size_net_impact_score: int = Field(default=0, ge=-5, le=5)
    profitability_net_impact_score: int = Field(default=0, ge=-5, le=5)
    short_term_direction: str = "uncertain"
    medium_term_direction: str = "uncertain"
    long_term_direction: str = "uncertain"
    method_confidence_score: int = Field(default=1, ge=1, le=5)
    sensitive_assumptions: list[str] = Field(default_factory=list, max_length=2)
    review_status: ForecastReviewStatus = ForecastReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None


class FutureScenario(BaseModel):
    scenario_id: str = Field(default_factory=lambda: f"SCN-{uuid4().hex[:10]}")
    scenario_type: ScenarioType
    title: str
    narrative: str
    trigger_conditions: list[str] = Field(min_length=1)
    expected_outcomes: list[str] = Field(min_length=1)
    trend_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    finding_ids: list[str] = Field(min_length=1)
    leading_indicators: list[str] = Field(min_length=1)
    falsification_conditions: list[str] = Field(min_length=1)
    likelihood_label: str
    review_status: ForecastReviewStatus = ForecastReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None


class FutureIntelligenceArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    industry_analysis_id: str
    evidence_collection_id: str
    input_evidence_ids: list[str] = Field(min_length=1)
    input_finding_ids: list[str] = Field(min_length=1)
    forecast_mode: str
    forecast_methodology: ForecastMethodology = Field(
        default_factory=lambda: ForecastMethodology(
            data_sufficiency="insufficient",
            structured_observation_count=0,
            selected_method=ForecastMethod.CAUSAL_SCENARIO,
            benchmark_method=ForecastMethod.NAIVE_BASELINE,
            candidate_methods=[ForecastMethod.CAUSAL_SCENARIO],
            validation_design="无同口径结构化历史序列，采用可证伪情景与领先指标持续校准。",
            error_metrics=["not_applicable"],
            prediction_interval="不输出伪精确数值区间",
            quantitative_forecast_used=False,
            selection_rationale="数据不足以训练和回测量化模型。",
            model_limitations=["当前输入缺少同一指标、同一口径的连续历史观测。"],
        )
    )
    trends: list[FutureTrend] = Field(min_length=1, max_length=8)
    scenarios: list[FutureScenario] = Field(min_length=3, max_length=3)
    monitoring_priorities: list[str] = Field(min_length=1)
    forecast_gaps: list[str] = Field(default_factory=list)
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
