"""HKGAI Search Platform MCP integration.

Credentials stay in transport headers and are never exposed as tool arguments or
model context. Search and crawl output is untrusted external content.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, AsyncContextManager, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from src.config import Settings
from src.models.evidence import CrawlResult, WebSearchResult
from src.providers.base import ProviderError


SEARCH_TOOL = "search_web"
CRAWL_TOOL = "crawl_page"


@dataclass(frozen=True, slots=True)
class MCPToolDefinition:
    name: str
    description: str | None
    input_schema: dict[str, Any]


SessionFactory = Callable[[], AsyncContextManager[ClientSession]]


class HKGAIMCPProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.settings = settings
        self._session_factory = session_factory

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "App-Name": self.settings.app_name,
            "App-Key": self.settings.app_key,
        }

    @asynccontextmanager
    async def _open_session(self):
        if self._session_factory is not None:
            async with self._session_factory() as session:
                yield session
            return

        try:
            async with streamablehttp_client(
                self.settings.search_mcp_url,
                headers=self._headers,
                timeout=30,
                sse_read_timeout=self.settings.search_timeout_seconds,
            ) as (read_stream, write_stream, _):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(
                        seconds=self.settings.search_timeout_seconds
                    ),
                ) as session:
                    await session.initialize()
                    yield session
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Search Platform MCP connection failed") from exc

    async def list_tools(self) -> list[MCPToolDefinition]:
        async with self._open_session() as session:
            try:
                result = await session.list_tools()
            except Exception as exc:
                raise ProviderError("MCP tools/list failed") from exc
        return [
            MCPToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
            )
            for tool in result.tools
        ]

    async def search_web(self, query: str) -> WebSearchResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("search query cannot be empty")
        result = await self._discover_and_call(SEARCH_TOOL, {"query": cleaned_query})
        payload = self._structured_payload(result, SEARCH_TOOL)
        try:
            return WebSearchResult.from_mcp_payload(payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

    async def crawl_page(self, url: str) -> CrawlResult:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise ValueError("crawl URL cannot be empty")
        result = await self._discover_and_call(CRAWL_TOOL, {"url": cleaned_url})
        payload = self._structured_payload(result, CRAWL_TOOL)
        try:
            return CrawlResult.from_mcp_payload(payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

    async def _discover_and_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        async with self._open_session() as session:
            try:
                tools_result = await session.list_tools()
                available = {tool.name: tool for tool in tools_result.tools}
                if tool_name not in available:
                    raise ProviderError(f"Required MCP tool is unavailable: {tool_name}")
                result = await session.call_tool(tool_name, arguments)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError(f"MCP tool call failed: {tool_name}") from exc
        if result.isError:
            raise ProviderError(f"MCP tool returned an error: {tool_name}")
        return result

    @staticmethod
    def _structured_payload(result: CallToolResult, tool_name: str) -> dict[str, Any]:
        payload = result.structuredContent
        if isinstance(payload, dict):
            return payload

        # Compatibility fallback: some MCP servers return JSON as TextContent.
        for item in result.content:
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
        raise ProviderError(f"MCP tool returned no structured JSON: {tool_name}")
