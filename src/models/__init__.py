"""Structured domain models used by the research workflow."""

from .evidence import (
    CrawlFailure,
    CrawlResult,
    CrawledPage,
    EvidenceCandidate,
    SearchHit,
    SearchResult,
    WebSearchResult,
)

__all__ = [
    "CrawlFailure",
    "CrawlResult",
    "CrawledPage",
    "EvidenceCandidate",
    "SearchHit",
    "SearchResult",
    "WebSearchResult",
]
