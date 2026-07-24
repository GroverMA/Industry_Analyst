"""Downloadable general-industry report artifact."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class PromptCoverageItem(BaseModel):
    question: str
    coverage_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    trend_ids: list[str] = Field(default_factory=list)
    note: str


class GeneralReportArtifact(BaseModel):
    report_id: str = Field(default_factory=lambda: f"RPT-{uuid4().hex[:10]}")
    title: str
    report_status: str = "human_reviewed_general_report"
    markdown: str
    accepted_evidence_ids: list[str] = Field(default_factory=list)
    accepted_finding_ids: list[str] = Field(default_factory=list)
    accepted_trend_ids: list[str] = Field(default_factory=list)
    accepted_scenario_ids: list[str] = Field(default_factory=list)
    prompt_coverage: list[PromptCoverageItem] = Field(default_factory=list)
    unresolved_prompt_questions: list[str] = Field(default_factory=list)
    source_count: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
