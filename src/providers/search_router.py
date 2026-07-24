"""Search transport routing with MCP-first automatic REST fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from src.models.evidence import CrawlResult, WebSearchResult
from src.providers.base import ProviderError
from src.providers.hkgai_mcp import HKGAIMCPProvider
from src.providers.hkgai_structured_rest import HKGAIStructuredRestProvider


Transport = Literal["mcp", "rest"]


@dataclass(frozen=True, slots=True)
class RoutedSearchResult:
    result: WebSearchResult
    transport: Transport
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RoutedCrawlResult:
    result: CrawlResult
    transport: Transport
    fallback_reason: str | None = None


class SearchRouter:
    """Keep a single external transport failure from breaking research.

    In auto mode, the first MCP execution error marks MCP unhealthy for this
    router instance. Later calls go directly to REST until an explicit reset.
    """

    def __init__(
        self,
        mcp: HKGAIMCPProvider,
        rest: HKGAIStructuredRestProvider,
        *,
        mode: str = "auto",
    ) -> None:
        if mode not in {"auto", "mcp", "rest"}:
            raise ValueError("search router mode must be auto, mcp, or rest")
        self.mcp = mcp
        self.rest = rest
        self.mode = mode
        self._mcp_healthy: bool | None = None
        self._fallback_reason: str | None = None

    @property
    def mcp_healthy(self) -> bool | None:
        return self._mcp_healthy

    @property
    def fallback_reason(self) -> str | None:
        return self._fallback_reason

    def reset_mcp_health(self) -> None:
        self._mcp_healthy = None
        self._fallback_reason = None

    async def search_web(self, query: str) -> RoutedSearchResult:
        if self.mode == "rest" or (self.mode == "auto" and self._mcp_healthy is False):
            result = await asyncio.to_thread(self.rest.search_web, query)
            return RoutedSearchResult(
                result=result,
                transport="rest",
                fallback_reason=self._fallback_reason,
            )
        try:
            result = await self.mcp.search_web(query)
            self._mcp_healthy = True
            return RoutedSearchResult(result=result, transport="mcp")
        except ProviderError as exc:
            if self.mode == "mcp":
                raise
            self._mcp_healthy = False
            self._fallback_reason = str(exc)
            result = await asyncio.to_thread(self.rest.search_web, query)
            return RoutedSearchResult(
                result=result,
                transport="rest",
                fallback_reason=self._fallback_reason,
            )

    async def crawl_page(self, url: str) -> RoutedCrawlResult:
        if self.mode == "rest" or (self.mode == "auto" and self._mcp_healthy is False):
            result = await asyncio.to_thread(self.rest.crawl_page, url)
            return RoutedCrawlResult(
                result=result,
                transport="rest",
                fallback_reason=self._fallback_reason,
            )
        try:
            result = await self.mcp.crawl_page(url)
            self._mcp_healthy = True
            return RoutedCrawlResult(result=result, transport="mcp")
        except ProviderError as exc:
            if self.mode == "mcp":
                raise
            self._mcp_healthy = False
            self._fallback_reason = str(exc)
            result = await asyncio.to_thread(self.rest.crawl_page, url)
            return RoutedCrawlResult(
                result=result,
                transport="rest",
                fallback_reason=self._fallback_reason,
            )
