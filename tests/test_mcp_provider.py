from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from src.config import Settings
from src.providers.hkgai_mcp import HKGAIMCPProvider


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name="search_web",
                    description="Search the web",
                    inputSchema={"type": "object", "properties": {"query": {}}},
                ),
                Tool(
                    name="crawl_page",
                    description="Crawl a page",
                    inputSchema={"type": "object", "properties": {"url": {}}},
                ),
            ]
        )

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        self.calls.append((name, arguments))
        if name == "search_web":
            payload = {
                "status": "success",
                "trace_id": "trace-search",
                "duration_ms": 120,
                "engine": "tavily",
                "data": {
                    "query": arguments["query"],
                    "response_time": 0.12,
                    "results": [
                        {
                            "title": "Official policy",
                            "url": "https://www.gov.cn/policy",
                            "content": "Policy summary",
                            "score": 0.95,
                        },
                        {
                            "title": "Duplicate",
                            "url": "https://www.gov.cn/policy",
                            "content": "Duplicate summary",
                            "score": 0.80,
                        },
                    ],
                },
            }
        else:
            payload = {
                "status": "success",
                "trace_id": "trace-crawl",
                "duration_ms": 80,
                "engine": "tavily",
                "data": {
                    "request_id": "request-1",
                    "response_time": 0.08,
                    "results": [
                        {
                            "url": arguments["url"],
                            "raw_content": "Untrusted external page content",
                        }
                    ],
                    "failed_results": [],
                },
            }
        return CallToolResult(
            content=[TextContent(type="text", text="structured result")],
            structuredContent=payload,
            isError=False,
        )


def settings() -> Settings:
    return Settings(
        model_api_key="test-secret",
        model_base_url="https://model.example",
        model_name="test-model",
        agenthub_endpoint="https://search.example/v1/tool/search-agent",
        search_mcp_url="https://mcp.example/mcp",
        app_name="test-app",
        app_key="test-key",
    )


def provider_and_session() -> tuple[HKGAIMCPProvider, FakeSession]:
    fake = FakeSession()

    @asynccontextmanager
    async def factory():
        yield fake

    return HKGAIMCPProvider(settings(), session_factory=factory), fake


def test_list_tools_uses_dynamic_server_definitions() -> None:
    provider, _ = provider_and_session()

    tools = asyncio.run(provider.list_tools())

    assert [tool.name for tool in tools] == ["search_web", "crawl_page"]
    assert tools[0].input_schema["type"] == "object"


def test_search_web_returns_structured_deduplicated_hits() -> None:
    provider, fake = provider_and_session()

    result = asyncio.run(provider.search_web("official policy"))

    assert result.trace_id == "trace-search"
    assert len(result.results) == 1
    assert result.results[0].domain == "www.gov.cn"
    assert fake.calls == [("search_web", {"query": "official policy"})]


def test_crawl_page_keeps_external_content_out_of_tool_arguments() -> None:
    provider, fake = provider_and_session()

    result = asyncio.run(provider.crawl_page("https://www.gov.cn/policy"))

    assert result.trace_id == "trace-crawl"
    assert result.pages[0].raw_content == "Untrusted external page content"
    assert fake.calls == [
        ("crawl_page", {"url": "https://www.gov.cn/policy"})
    ]
    assert "test-key" not in repr(fake.calls)
