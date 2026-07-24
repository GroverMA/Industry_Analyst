#!/usr/bin/env python3
"""Verify MCP auth headers are present on every HTTP request without printing them."""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from src.config import Settings  # noqa: E402


async def main() -> None:
    settings = Settings.load()

    async def inspect_request(request: httpx.Request) -> None:
        app_name = request.headers.get("App-Name")
        app_key = request.headers.get("App-Key")
        print(
            f"[REQUEST] {request.method} {request.url.path} "
            f"app_name_present={app_name is not None} "
            f"app_name_length={len(app_name or '')} "
            f"app_key_present={app_key is not None} "
            f"app_key_length={len(app_key or '')}"
        )

    async def inspect_response(response: httpx.Response) -> None:
        print(f"[RESPONSE] {response.status_code} {response.request.url.path}")

    def client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=True,
            event_hooks={
                "request": [inspect_request],
                "response": [inspect_response],
            },
        )

    async with streamablehttp_client(
        settings.search_mcp_url,
        headers={"App-Name": settings.app_name, "App-Key": settings.app_key},
        timeout=30,
        sse_read_timeout=settings.search_timeout_seconds,
        httpx_client_factory=client_factory,
    ) as (read_stream, write_stream, _):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(
                seconds=settings.search_timeout_seconds
            ),
        ) as session:
            await session.initialize()
            await session.list_tools()
            result = await session.call_tool(
                "search_web", {"query": "中国分子诊断行业政策"}
            )
            print(f"[TOOL RESULT] isError={result.isError}")


if __name__ == "__main__":
    asyncio.run(main())
