#!/usr/bin/env python3
"""Safely diagnose MCP tool schemas and one minimal search call."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from src.config import Settings  # noqa: E402


async def main() -> None:
    settings = Settings.load()
    headers = {"App-Name": settings.app_name, "App-Key": settings.app_key}
    async with streamablehttp_client(
        settings.search_mcp_url,
        headers=headers,
        timeout=30,
        sse_read_timeout=settings.search_timeout_seconds,
    ) as (read_stream, write_stream, _):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(
                seconds=settings.search_timeout_seconds
            ),
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print(
                    f"[SCHEMA] {tool.name}: "
                    f"{json.dumps(tool.inputSchema, ensure_ascii=False)}"
                )

            result = await session.call_tool(
                "search_web", {"query": "中国分子诊断行业政策"}
            )
            print(f"[CALL] isError={result.isError}")
            if isinstance(result.structuredContent, dict):
                safe = {
                    key: result.structuredContent.get(key)
                    for key in ("status", "trace_id", "duration_ms", "engine")
                    if key in result.structuredContent
                }
                data = result.structuredContent.get("data")
                if isinstance(data, dict):
                    safe["data_fields"] = sorted(str(key) for key in data)
                    safe["result_count"] = len(data.get("results", [])) if isinstance(
                        data.get("results"), list
                    ) else None
                    safe["error"] = data.get("error")
                print(f"[STRUCTURED] {json.dumps(safe, ensure_ascii=False)}")
            for item in result.content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    print(f"[MESSAGE] {text[:500]}")


if __name__ == "__main__":
    asyncio.run(main())
