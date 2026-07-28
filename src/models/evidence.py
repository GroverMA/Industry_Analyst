"""Evidence candidate structures.

Agenthub URLs are discovery candidates, not verified evidence. A later workflow
stage will fetch, classify, corroborate, and review them before they can support
a material claim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _absolute_http_url(value: str) -> str:
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    return cleaned


class EvidenceCandidate(BaseModel):
    url: str
    domain: str
    discovery_query: str
    verified: bool = False
    source_tier: str | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        return _absolute_http_url(value)


class SearchResult(BaseModel):
    query: str
    reasoning: str = ""
    used_urls: list[str] = Field(default_factory=list)
    candidates: list[EvidenceCandidate] = Field(default_factory=list)
    raw_data_fields: list[str] = Field(default_factory=list)

    @classmethod
    def from_agenthub(cls, query: str, payload: dict) -> "SearchResult":
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Agenthub response is missing a data object")

        reasoning = data.get("reasoning", "")
        raw_urls = data.get("used_urls", [])
        if reasoning is None:
            reasoning = ""
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)
        if not isinstance(raw_urls, list):
            raise ValueError("Agenthub data.used_urls must be a list")

        unique_urls: list[str] = []
        seen: set[str] = set()
        for item in raw_urls:
            if not isinstance(item, str):
                continue
            url = item.strip()
            if not url or url in seen:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            seen.add(url)
            unique_urls.append(url)

        candidates = [
            EvidenceCandidate(
                url=url,
                domain=urlparse(url).netloc.lower(),
                discovery_query=query,
            )
            for url in unique_urls
        ]
        return cls(
            query=query,
            reasoning=reasoning,
            used_urls=unique_urls,
            candidates=candidates,
            raw_data_fields=sorted(str(key) for key in data),
        )


class SearchHit(BaseModel):
    """A structured MCP search result, still unverified as evidence."""

    title: str
    url: str
    content: str = ""
    score: float | None = None
    domain: str = ""

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        return _absolute_http_url(value)

    @classmethod
    def from_payload(cls, payload: dict) -> "SearchHit":
        url = _absolute_http_url(str(payload.get("url", "")))
        raw_score = payload.get("score")
        score = None
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
            score = float(raw_score)
        return cls(
            title=str(payload.get("title") or "Untitled source"),
            url=url,
            content=str(payload.get("content") or ""),
            score=score,
            domain=urlparse(url).netloc.lower(),
        )


class WebSearchResult(BaseModel):
    query: str
    results: list[SearchHit] = Field(default_factory=list)
    trace_id: str | None = None
    duration_ms: int | float | None = None
    engine: str | None = None
    response_time: int | float | None = None

    @classmethod
    def from_mcp_payload(cls, payload: dict) -> "WebSearchResult":
        if payload.get("status") != "success":
            raise ValueError("MCP search tool returned a non-success status")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("MCP search response is missing a data object")
        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            raise ValueError("MCP search data.results must be a list")

        results: list[SearchHit] = []
        seen: set[str] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                hit = SearchHit.from_payload(item)
            except ValueError:
                continue
            if hit.url in seen:
                continue
            seen.add(hit.url)
            results.append(hit)

        return cls(
            query=str(data.get("query") or ""),
            results=results,
            trace_id=(str(payload["trace_id"]) if payload.get("trace_id") else None),
            duration_ms=payload.get("duration_ms"),
            engine=(str(payload["engine"]) if payload.get("engine") else None),
            response_time=data.get("response_time"),
        )

    @classmethod
    def from_rest_payload(cls, payload: dict) -> "WebSearchResult":
        if payload.get("status") != "success":
            raise ValueError("REST search returned a non-success status")
        data = payload.get("search_results")
        if not isinstance(data, dict):
            raise ValueError("REST search response is missing search_results")
        return cls.from_mcp_payload(
            {
                "status": "success",
                "engine": payload.get("engine"),
                "data": data,
            }
        )


class CrawledPage(BaseModel):
    url: str
    raw_content: str

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        return _absolute_http_url(value)


class CrawlFailure(BaseModel):
    url: str
    error: str = ""

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        return _absolute_http_url(value)


class CrawlResult(BaseModel):
    pages: list[CrawledPage] = Field(default_factory=list)
    failures: list[CrawlFailure] = Field(default_factory=list)
    trace_id: str | None = None
    duration_ms: int | float | None = None
    engine: str | None = None
    request_id: str | None = None
    response_time: int | float | None = None

    @classmethod
    def from_mcp_payload(cls, payload: dict) -> "CrawlResult":
        if payload.get("status") != "success":
            raise ValueError("MCP crawl tool returned a non-success status")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("MCP crawl response is missing a data object")

        raw_pages = data.get("results", [])
        raw_failures = data.get("failed_results", [])
        if not isinstance(raw_pages, list) or not isinstance(raw_failures, list):
            raise ValueError("MCP crawl result lists are invalid")

        pages: list[CrawledPage] = []
        for item in raw_pages:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                pages.append(
                    CrawledPage(
                        url=str(item["url"]),
                        raw_content=str(item.get("raw_content") or ""),
                    )
                )
            except ValueError:
                continue

        failures: list[CrawlFailure] = []
        for item in raw_failures:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                failures.append(
                    CrawlFailure(
                        url=str(item["url"]),
                        error=str(item.get("error") or ""),
                    )
                )
            except ValueError:
                continue

        return cls(
            pages=pages,
            failures=failures,
            trace_id=(str(payload["trace_id"]) if payload.get("trace_id") else None),
            duration_ms=payload.get("duration_ms"),
            engine=(str(payload["engine"]) if payload.get("engine") else None),
            request_id=(str(data["request_id"]) if data.get("request_id") else None),
            response_time=data.get("response_time"),
        )

    @classmethod
    def from_rest_payload(cls, payload: dict) -> "CrawlResult":
        if payload.get("status") != "success":
            raise ValueError("REST crawler returned a non-success status")
        data = payload.get("crawler_results")
        if not isinstance(data, dict):
            raise ValueError("REST crawler response is missing crawler_results")
        return cls.from_mcp_payload(
            {
                "status": "success",
                "engine": payload.get("engine"),
                "data": data,
            }
        )


class SourceTier(StrEnum):
    """Default public-source hierarchy used before industry-pack overrides."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EvidenceKind(StrEnum):
    FACT = "fact"
    DATA = "data"
    VIEWPOINT = "viewpoint"
    INFERENCE = "inference"
    FORECAST = "forecast"


class EvidenceReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"
    OUT_OF_SCOPE = "out_of_scope"
    LOW_RELIABILITY = "low_reliability"
    UNSUPPORTED = "unsupported"


class EvidenceSource(BaseModel):
    source_id: str = Field(default_factory=lambda: f"SRC-{uuid4().hex[:10]}")
    task_id: str
    discovery_query: str
    title: str
    url: str
    domain: str
    snippet: str = ""
    search_score: float | None = None
    source_tier: SourceTier
    tier_reason: str
    transport: str
    fallback_reason: str | None = None
    crawled: bool = False
    crawl_transport: str | None = None
    crawl_fallback_reason: str | None = None
    content_characters: int = 0

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        return _absolute_http_url(value)


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"EVD-{uuid4().hex[:10]}")
    task_id: str
    source_id: str
    kind: EvidenceKind
    statement: str
    supporting_excerpt: str
    source_date: str | None = None
    geographic_scope: str
    market_scope: str
    supports_or_challenges: str
    model_confidence: float = Field(ge=0, le=1)
    prompt_relevance: float = Field(default=0.0, ge=0, le=1)
    question_ids: list[str] = Field(default_factory=list)
    prompt_question_ids: list[str] = Field(default_factory=list)
    qa_score: int = Field(ge=0, le=100)
    qa_breakdown: dict[str, int] = Field(default_factory=dict)
    qa_flags: list[str] = Field(default_factory=list)
    review_status: EvidenceReviewStatus = EvidenceReviewStatus.NEEDS_REVIEW
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None


class EvidenceConflict(BaseModel):
    conflict_id: str = Field(default_factory=lambda: f"CNF-{uuid4().hex[:10]}")
    task_id: str
    description: str
    evidence_ids: list[str] = Field(min_length=2)
    resolution_note: str | None = None


class TaskEvidenceRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"RUN-{uuid4().hex[:10]}")
    task_id: str
    task_title: str
    queries_used: list[str] = Field(min_length=1)
    sources: list[EvidenceSource] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    search_errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceCollectionArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    research_plan_id: str
    task_runs: list[TaskEvidenceRun] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_confirmed: bool = False
    coverage_gap_resolution: str | None = None
    coverage_gap_user_input: str | None = None
    coverage_gaps_acknowledged_at: datetime | None = None

    def run_for(self, task_id: str) -> TaskEvidenceRun | None:
        return next((run for run in self.task_runs if run.task_id == task_id), None)

    @property
    def sources(self) -> list[EvidenceSource]:
        return [source for run in self.task_runs for source in run.sources]

    @property
    def evidence(self) -> list[EvidenceItem]:
        return [item for run in self.task_runs for item in run.evidence]
