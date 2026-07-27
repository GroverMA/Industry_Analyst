"""Structured research artifacts produced before evidence collection."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MethodologyTrace(BaseModel):
    sop_id: str
    sop_name: str
    sop_version: str
    sop_hash: str
    locked: bool = True
    rule_ids: list[str] = Field(min_length=1)
    compliance_checks: list[str] = Field(default_factory=list)


class ResearchIntent(BaseModel):
    """Semantic interpretation of the user's original research prompt.

    The vocabulary is deliberately user-facing.  Internal analysis taxonomies
    are mapped later so users do not need to phrase questions as "drivers" or
    any other system keyword.
    """

    interpreted_objective: str = ""
    requested_topics: list[str] = Field(default_factory=list)
    must_answer_questions: list[str] = Field(default_factory=list)
    terminology_map: dict[str, str] = Field(default_factory=dict)
    explicit_exclusions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class MarketDefinition(BaseModel):
    core_market: str
    product_scope: str
    customer_scope: str
    geography_scope: str
    value_chain_scope: str
    time_scope: str
    inclusions: list[str] = Field(min_length=1)
    exclusions: list[str] = Field(min_length=1)
    market_sizing_basis: str = "尚待明确"
    competitor_definition: str = "在同一客户需求、预算或应用场景中形成可解释替代关系的市场参与者"
    adjacent_markets: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)

    @field_validator(
        "core_market",
        "product_scope",
        "customer_scope",
        "geography_scope",
        "value_chain_scope",
        "time_scope",
    )
    @classmethod
    def require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("market definition fields cannot be empty")
        return cleaned


class ResearchBriefArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    decision_statement: str
    original_prompt: str = ""
    interpreted_intent: ResearchIntent = Field(default_factory=ResearchIntent)
    market_definition: MarketDefinition
    key_questions: list[str] = Field(min_length=1)
    information_gaps: list[str] = Field(min_length=1)
    hypotheses: list[str] = Field(min_length=1)
    clarification_questions: list[str] = Field(default_factory=list)
    confidence_note: str
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
    confirmed_at: datetime | None = None


class ResearchTask(BaseModel):
    task_id: str
    title: str
    objective: str
    questions: list[str] = Field(min_length=1)
    hypotheses: list[str] = Field(min_length=1)
    information_needs: list[str] = Field(min_length=1)
    preferred_sources: list[str] = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1)
    deliverables: list[str] = Field(min_length=1)
    evidence_standard: str
    counter_evidence_required: bool = True
    validation_gate: str
    depends_on: list[str] = Field(default_factory=list)


class ResearchPlanArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    plan_summary: str
    tasks: list[ResearchTask] = Field(min_length=1)
    human_review_gates: list[str] = Field(min_length=1)
    unresolved_gaps: list[str] = Field(default_factory=list)
    sop_coverage: dict[str, list[str]] = Field(default_factory=dict)
    methodology: MethodologyTrace
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
