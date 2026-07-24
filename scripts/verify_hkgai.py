#!/usr/bin/env python3
"""Run the minimum real HKGAI connectivity and structure checks.

This script never prints credentials. Search is opt-in because one Agenthub call
may take several minutes and may retrieve a large amount of text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigurationError, Settings  # noqa: E402
from src.providers import (  # noqa: E402
    ChatMessage,
    HKGAIModelProvider,
    HKGAIMCPProvider,
    HKGAISearchProvider,
    HKGAIStructuredRestProvider,
    ProviderError,
    SearchRouter,
)


SEARCH_PROBE = """请只查找2024年至2026年由中国国家医保局、国家药监局、
国家卫生健康委员会或省级政府部门正式发布的、直接影响分子诊断或体外诊断
试剂采购与准入的政策文件。排除药品、中成药、百科和商业报告推广页面。
最多返回5个最相关的官方来源；找不到时请明确说明，不要补充无关来源。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-router",
        action="store_true",
        help="run MCP-first search and crawl with automatic structured REST fallback",
    )
    parser.add_argument(
        "--with-mcp",
        action="store_true",
        help="discover MCP tools, run one search_web call, and crawl one result",
    )
    parser.add_argument(
        "--with-search-agent",
        action="store_true",
        help="also run the synchronous REST Search Agent fallback",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="enable HKGAI V3 thinking for the model probe",
    )
    return parser.parse_args()


async def verify_mcp(settings: Settings) -> None:
    mcp = HKGAIMCPProvider(settings)
    started = time.perf_counter()
    tools = await mcp.list_tools()
    elapsed = time.perf_counter() - started
    tool_names = [tool.name for tool in tools]
    print(f"[MCP TOOLS] OK: {', '.join(tool_names)}, {elapsed:.2f}s")

    required = {"search_web", "crawl_page"}
    missing = sorted(required - set(tool_names))
    if missing:
        raise ProviderError(f"Required MCP tools unavailable: {', '.join(missing)}")

    started = time.perf_counter()
    result = await mcp.search_web(SEARCH_PROBE)
    elapsed = time.perf_counter() - started
    print(
        f"[MCP SEARCH] OK: {len(result.results)} unique hit(s), {elapsed:.2f}s, "
        f"trace_id={result.trace_id or 'not reported'}"
    )
    for hit in result.results[:5]:
        score = f"{hit.score:.3f}" if hit.score is not None else "not reported"
        print(f"  - score={score} {hit.domain}: {hit.url}")

    if not result.results:
        print("[MCP CRAWL] SKIPPED: search_web returned no URL")
        return

    target = result.results[0].url
    started = time.perf_counter()
    crawl = await mcp.crawl_page(target)
    elapsed = time.perf_counter() - started
    content_chars = sum(len(page.raw_content) for page in crawl.pages)
    print(
        f"[MCP CRAWL] OK: pages={len(crawl.pages)}, failures={len(crawl.failures)}, "
        f"content_chars={content_chars}, {elapsed:.2f}s, "
        f"trace_id={crawl.trace_id or 'not reported'}"
    )
    print("[MCP CONTENT] External page text was not printed or treated as instructions")


async def verify_router(settings: Settings) -> None:
    mcp = HKGAIMCPProvider(settings)
    rest = HKGAIStructuredRestProvider(settings)
    router = SearchRouter(mcp, rest, mode=settings.search_transport)

    started = time.perf_counter()
    routed_search = await router.search_web(SEARCH_PROBE)
    elapsed = time.perf_counter() - started
    result = routed_search.result
    print(
        f"[SEARCH ROUTER] OK: transport={routed_search.transport}, "
        f"hits={len(result.results)}, {elapsed:.2f}s"
    )
    if routed_search.fallback_reason:
        print(f"[SEARCH FALLBACK] {routed_search.fallback_reason}")
    for hit in result.results[:5]:
        score = f"{hit.score:.3f}" if hit.score is not None else "not reported"
        print(f"  - score={score} {hit.domain}: {hit.url}")

    if not result.results:
        raise ProviderError("Search router returned no traceable URL")

    target = result.results[0].url
    started = time.perf_counter()
    routed_crawl = await router.crawl_page(target)
    elapsed = time.perf_counter() - started
    crawl = routed_crawl.result
    content_chars = sum(len(page.raw_content) for page in crawl.pages)
    print(
        f"[CRAWL ROUTER] OK: transport={routed_crawl.transport}, "
        f"pages={len(crawl.pages)}, failures={len(crawl.failures)}, "
        f"content_chars={content_chars}, {elapsed:.2f}s"
    )
    if not crawl.pages:
        raise ProviderError("Search router could not crawl the selected page")
    print("[EXTERNAL CONTENT] Page text was not printed or treated as instructions")


def main() -> int:
    args = parse_args()
    try:
        settings = Settings.load()
    except ConfigurationError as exc:
        print(f"[CONFIG] FAILED: {exc}")
        return 2

    model = HKGAIModelProvider(settings)
    search = HKGAISearchProvider(settings)

    try:
        started = time.perf_counter()
        models = model.list_models()
        elapsed = time.perf_counter() - started
        selected = settings.model_name in models
        print(f"[MODEL LIST] OK: {len(models)} model(s), {elapsed:.2f}s")
        print(f"[MODEL SELECTED] {'OK' if selected else 'WARNING'}: {settings.model_name}")

        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是通用行业研究任务解析器。严格返回JSON对象，不得输出Markdown。"
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "将研究任务转换为JSON：行业=工业机器人；地区=全球；"
                    "目标=识别竞争者、驱动因素和未来三年趋势。必须包含industry、"
                    "region、research_objective、key_questions、information_gaps。"
                ),
            ),
        ]
        started = time.perf_counter()
        parsed, response = model.complete_json(
            messages, enable_thinking=args.thinking
        )
        elapsed = time.perf_counter() - started
        required = {
            "industry",
            "region",
            "research_objective",
            "key_questions",
            "information_gaps",
        }
        missing = sorted(required - parsed.keys())
        if missing:
            print(f"[MODEL JSON] FAILED: missing fields {', '.join(missing)}")
            return 1
        total_tokens = response.usage.get("total_tokens", "not reported")
        print(f"[MODEL JSON] OK: {elapsed:.2f}s, total_tokens={total_tokens}")

        if args.with_router:
            asyncio.run(verify_router(settings))
        else:
            print("[SEARCH ROUTER] SKIPPED: pass --with-router for resilient search/crawl")

        if args.with_mcp:
            asyncio.run(verify_mcp(settings))
        else:
            print("[MCP] SKIPPED: pass --with-mcp to test search_web and crawl_page")

        if args.with_search_agent:
            started = time.perf_counter()
            result = search.search(SEARCH_PROBE)
            elapsed = time.perf_counter() - started
            print(
                f"[AGENTHUB] OK: {len(result.candidates)} unique candidate(s), "
                f"{elapsed:.2f}s"
            )
            print(f"[AGENTHUB FIELDS] {', '.join(result.raw_data_fields)}")
            for candidate in result.candidates:
                print(f"  - {candidate.domain}: {candidate.url}")
            if not result.candidates:
                print("[AGENTHUB QUALITY] WARNING: no traceable URL returned")
        else:
            print(
                "[SEARCH AGENT] SKIPPED: pass --with-search-agent to test the fallback"
            )

    except ProviderError as exc:
        print(f"[PROVIDER] FAILED: {exc}")
        return 1

    print("[RESULT] Stage 1 connectivity checks completed without exposing secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
