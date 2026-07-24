# HKGAI Capability Validation

## Purpose

Stage 1 validates the competition-provided model and search capabilities before
the product workflow is built. It deliberately separates technical connectivity
from research-quality acceptance.

## Confirmed interfaces

### Modelhub

- Base URL: `https://test-new-api.hkchat.app`
- Models: `GET /v1/models`
- Chat: `POST /v1/chat/completions`
- Initial model: `t2_hkgai-v3_fp8_1m_e7`
- Authentication: Bearer token
- HKGAI V3 thinking: optional and disabled by default to control latency and cost

The manual playground test returned valid Chinese JSON with HTTP 200 in about
2.6 seconds. Runtime code still checks `/v1/models`; the documented model name
must not be assumed to remain available forever.

The first live code validation passed on 24 July 2026:

- `/v1/models`: one model returned in 1.61 seconds;
- selected model `t2_hkgai-v3_fp8_1m_e7`: available;
- general-industry JSON probe: valid output in 1.30 seconds;
- reported total tokens: 303.

### Agenthub Search Agent

- Endpoint: `https://search-agent.prod.hkchat.app/v1/tool/search-agent`
- Authentication headers: `App-Name` and `App-Key`
- Request body: `{ "query": "..." }`
- Confirmed response fields: `data.reasoning`, `data.used_urls`

The first broad molecular-diagnostics probe discovered many URLs but retrieved
about 47,786 tokens of page text. Results included relevant sources, weak sources,
and unrelated procurement material. Therefore:

1. Agenthub is a discovery provider, not an evidence authority.
2. `used_urls` become unverified `EvidenceCandidate` records.
3. The planner must issue narrow, atomic searches.
4. Later stages must rank, fetch, extract, corroborate, and review sources.
5. Search calls need visible latency and candidate-count monitoring.

### Search Platform MCP

- URL: `https://search-agent-mcp.prod.hkchat.app/mcp`
- Transport: MCP Streamable HTTP
- Authentication headers: `App-Name` and `App-Key`
- Dynamic discovery: `tools/list`
- Primary tools: `search_web(query)` and `crawl_page(url)`

`search_web` is the MVP's primary discovery path because it returns a structured
title, URL, content summary, and relevance score. After source ranking, only a
small number of selected URLs are sent to `crawl_page` for full text. This avoids
the broad Search Agent pattern that retrieved tens of thousands of tokens in one
call.

MCP credentials remain in HTTP headers and never become model-visible tool
arguments. All returned summaries and page text are untrusted external content;
they may be evidence candidates but never system instructions.

### Current live MCP status

The first live MCP validation on 24 July 2026 established that:

- the Streamable HTTP connection initialized successfully;
- `tools/list` returned `crawl_page` and `search_web` in 3.90 seconds;
- both live input schemas matched the downloaded integration guide;
- `search_web` returned MCP `isError=true` with upstream status 403 and
  `authentication service unavailable`;
- an empty-query request to the REST fallback reached request validation and
  returned HTTP 400 `Missing required field: query`.

Therefore MCP transport and tool discovery pass, but MCP tool execution remains
unaccepted until the provider-side authentication/ACL condition is resolved.
Do not silently convert this external failure into an empty search result.

### MCP self-audit and REST control test

After the organizer reported no general platform issue, the client path was
audited again without printing credential values:

- the model key, App-Name, and App-Key matched the documented formats;
- all four MCP HTTP requests contained both App authentication headers;
- header lengths remained consistent across initialize, list, and call requests;
- every MCP HTTP response was 200 or 202;
- the tool result still returned `isError=true` with upstream status 403;
- a second MCP trace reproduced the same error:
  `search-platform-mcp-c808d54e37f241848411b8e6f97fac67`.

The same App credentials then passed two structured REST control tests:

1. `POST /v1/search` with `mode=transparent`, `engine=tavily`, and
   `search_param.query` returned HTTP 200 and structured
   `title/url/content/score` results in 3.99 seconds.
2. `POST /v1/crawler` with `mode=transparent`, `engine=tavily`, and
   `crawler_param.urls` returned HTTP 200, one page, zero failures, and 15,682
   characters of page content in 4.24 seconds.

This isolates the failure to MCP-side credential forwarding or account-specific
MCP permission mapping. The MVP can preserve the same evidence contract through
structured REST search/crawl while keeping MCP as an automatically re-testable
transport option.

### Final resilient route validation

The completed `SearchRouter` was then validated with real services. It attempted
MCP first, observed the tool-execution failure, switched automatically to
structured REST, returned five search hits, and crawled one selected source with
zero failures. The crawl returned 36,782 characters. The complete model, search,
fallback, and crawl script exited successfully without printing credentials or
external page content.

See [stage_1_acceptance.md](stage_1_acceptance.md) for the complete stage gate.

## Run locally

1. Copy `.env.example` to `.env`.
2. Put newly issued credentials in `.env`; never reuse credentials exposed in a
   screenshot.
3. Install `requirements.txt` in a virtual environment.
4. Run the model-only check:

   ```bash
   python scripts/verify_hkgai.py
   ```

5. Test dynamic MCP tool discovery, structured search, and one selected crawl:

   ```bash
   python scripts/verify_hkgai.py --with-mcp
   ```

6. Test the synchronous REST Search Agent fallback only when explicitly needed:

   ```bash
   python scripts/verify_hkgai.py --with-search-agent
   ```

The script reports status, latency, token usage when available, candidate counts,
domains, and URLs. It never prints credentials or raw request headers.

## Stage decision

- Use a provider-neutral Python orchestration layer.
- Use MCP `search_web` and `crawl_page` as the primary evidence-discovery path.
- Keep REST `/tool/search-agent` as an optional fast-research fallback.
- Use direct REST calls for the MVP because both HKGAI interfaces are documented
  and the custom thinking parameters are explicit.
- Do not make OpenAI Agents SDK, LangGraph, LangChain, or Dify a Stage 1 dependency.
- Reassess orchestration frameworks only after the research workflow and state
  transitions are stable.
