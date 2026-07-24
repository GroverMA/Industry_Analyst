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


class PlayerMoveStatus(StrEnum):
    OBSERVED = "observed"
    ANNOUNCED = "announced"
    INFERRED = "inferred"


class ScenarioType(StrEnum):
    BASELINE = "baseline"
    ACCELERATED = "accelerated"
    BLOCKED = "blocked"


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
    trends: list[FutureTrend] = Field(min_length=1, max_length=8)
    scenarios: list[FutureScenario] = Field(min_length=3, max_length=3)
    monitoring_priorities: list[str] = Field(min_length=1)
    forecast_gaps: list[str] = Field(default_factory=list)
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
