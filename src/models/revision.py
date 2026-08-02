"""Iterative reviewer conversations and durable report versions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class RevisionTarget(StrEnum):
    REPORT = "report"
    REFERENCE_CHECK = "reference_check"
    INDUSTRY_ANALYSIS = "industry_analysis"
    FUTURE_INTELLIGENCE = "future_intelligence"
    COMPANY_SCORECARD = "company_scorecard"
    ACTION_PLAN = "action_plan"


class ReportVersion(BaseModel):
    version: int = Field(ge=1)
    markdown: str
    source: str
    reviewer_note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RevisionTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: f"REV-{uuid4().hex[:10]}")
    reviewer_message: str
    targets: list[RevisionTarget] = Field(min_length=1)
    assistant_analysis: str
    recommendations: list[str] = Field(default_factory=list)
    questions_for_reviewer: list[str] = Field(default_factory=list)
    trace_amendments: dict[str, str] = Field(default_factory=dict)
    proposed_markdown: str
    accepted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContentRevisionArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"CRV-{uuid4().hex[:10]}")
    project_id: str
    report_kind: str
    versions: list[ReportVersion] = Field(default_factory=list)
    turns: list[RevisionTurn] = Field(default_factory=list)
    active_version: int = Field(default=1, ge=1)
    finalized: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
