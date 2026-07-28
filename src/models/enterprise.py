"""Private enterprise sensing inputs kept separate from public evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class EnterpriseEvidenceCategory(StrEnum):
    STRATEGIC_INTENT = "strategic_intent"
    INTERNAL_DOCUMENT = "internal_document"
    SALES_CHANNEL = "sales_channel"
    CUSTOMER = "customer"
    PRODUCT = "product"
    OPERATIONS = "operations"
    FINANCE = "finance"
    RESEARCH_DEVELOPMENT = "research_development"
    ORGANIZATION_RESOURCES = "organization_resources"
    MANAGEMENT_EXPERT = "management_expert"
    SELF_DIAGNOSIS = "self_diagnosis"


class EnterpriseDataDimension(StrEnum):
    SELL_IN = "sell_in"
    SELL_OUT = "sell_out"
    CUSTOMER_PENETRATION = "customer_penetration"
    INVENTORY = "inventory"
    PRICE_MARGIN = "price_margin"
    CHANNEL_COVERAGE = "channel_coverage"
    PRODUCT_PORTFOLIO = "product_portfolio"
    OPERATIONS_SUPPLY = "operations_supply"
    FINANCIAL_RESOURCE = "financial_resource"
    ORGANIZATION_CAPABILITY = "organization_capability"
    OTHER = "other"


class EnterpriseStatementType(StrEnum):
    FACT = "fact"
    OBSERVATION = "observation"
    VIEWPOINT = "viewpoint"
    HYPOTHESIS = "hypothesis"
    STRATEGIC_INTENT = "strategic_intent"
    MIXED_DOCUMENT = "mixed_document"


class EnterpriseSensitivity(StrEnum):
    REDACTED_DEMO = "redacted_demo"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EnterpriseReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EnterpriseEvidenceItem(BaseModel):
    enterprise_evidence_id: str = Field(
        default_factory=lambda: f"ENT-{uuid4().hex[:10]}"
    )
    title: str
    category: EnterpriseEvidenceCategory
    statement_type: EnterpriseStatementType
    content: str
    source_owner: str
    observed_at: str | None = None
    strategic_relevance: str
    data_dimension: EnterpriseDataDimension | None = None
    reporting_period: str | None = None
    sensitivity: EnterpriseSensitivity = EnterpriseSensitivity.REDACTED_DEMO
    project_only_permission: bool = True
    input_method: str = "manual"
    file_name: str | None = None
    file_sha256: str | None = None
    review_status: EnterpriseReviewStatus = EnterpriseReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title", "content", "source_owner", "strategic_relevance")
    @classmethod
    def require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("enterprise evidence fields cannot be empty")
        return cleaned


class EnterpriseSensingArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    target_company_snapshot: str | None = None
    strategy_objective_snapshot: str | None = None
    entries: list[EnterpriseEvidenceItem] = Field(default_factory=list)
    consent_to_model_processing: bool = False
    public_demo_acknowledged: bool = False
    human_confirmed: bool = False
    confirmed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def accepted_entries(self) -> list[EnterpriseEvidenceItem]:
        return [
            item
            for item in self.entries
            if item.review_status == EnterpriseReviewStatus.ACCEPTED
        ]
