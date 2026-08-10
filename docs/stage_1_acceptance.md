# Stage 1 Acceptance — HKGAI Capability Foundation

**Status:** Passed  
**Acceptance date:** 24 July 2026

## 1. Stage objective

Establish a safe, provider-neutral, genuinely callable foundation for the
universal Industry Analyst OS before any Streamlit workflow is built.

Stage 1 had to prove that the application can:

- call the competition-provided text model;
- discover current model IDs;
- produce parseable Chinese structured output;
- discover MCP search tools dynamically;
- search the web and crawl selected pages;
- survive a single transport failure through automatic fallback;
- keep all credentials out of source code, logs, and model context;
- treat search results as unverified evidence candidates.

## 2. Accepted architecture

```text
Research workflow
  -> SearchRouter
     -> MCP search_web / crawl_page (preferred)
     -> structured REST /search /crawler (automatic fallback)
     -> synchronous Search Agent (explicit use only)
  -> typed candidate evidence
  -> later evidence ranking, verification, and human review
```

Model calls use HKGAI Modelhub directly through its documented
OpenAI-compatible REST contract. Search and crawl transports share the same
`WebSearchResult` and `CrawlResult` domain structures, so the later Streamlit UI
and research workflow do not depend on a specific transport.

## 3. Implemented capabilities

### Configuration and safety

- local `.env` and Streamlit Secrets support;
- public defaults for non-secret endpoints and model ID;
- no credentials hard-coded in Python;
- `.env` and `.streamlit/secrets.toml` ignored by Git;
- missing or invalid configuration fails explicitly;
- search transport modes: `auto`, `mcp`, and `rest`.

### Modelhub

- `GET /v1/models`;
- `POST /v1/chat/completions`;
- non-streaming completion;
- optional HKGAI V3 thinking parameters;
- strict JSON parsing;
- safe timeout and HTTP error handling.

### Search and crawl

- MCP Streamable HTTP client;
- MCP `tools/list` discovery;
- MCP `search_web(query)`;
- MCP `crawl_page(url)`;
- structured REST transparent Tavily search;
- structured REST transparent Tavily crawler;
- synchronous REST Search Agent retained as an explicit fallback only;
- title, URL, summary, score, domain, full text, failures, engine, duration,
  request ID, and trace ID parsing where available;
- URL validation and deduplication;
- one retry only for timeout or HTTP 502/503/504 on structured REST;
- MCP failure remembered for the router lifetime to avoid repeated failed calls;
- explicit reset method for later MCP health re-check.

### Evidence boundary

- search hits are candidates, not verified evidence;
- full page text is untrusted external content;
- external content is never printed by the validation path or treated as a
  system instruction;
- transport failure cannot silently become an empty research conclusion.

## 4. Automated tests

Result:

```text
13 passed
```

Coverage includes:

- Bearer model authentication;
- model-list parsing;
- structured JSON parsing;
- HKGAI thinking parameters;
- Search Agent request and response parsing;
- MCP dynamic tool definitions;
- MCP search and crawl parsing;
- URL validation and deduplication;
- structured REST request bodies;
- structured REST response parsing;
- MCP-first routing;
- automatic REST fallback;
- sticky MCP failure state;
- forced REST mode;
- credential exclusion from MCP tool arguments.

## 5. Final live end-to-end result

Command:

```bash
python scripts/verify_hkgai.py --with-router
```

Observed result:

```text
Model list:       OK — 1 model, 2.64s
Selected model:   OK — t2_hkgai-v3_fp8_1m_e7
Model JSON:       OK — 1.11s, 282 total tokens
Search Router:    OK — REST fallback, 5 hits, 9.35s
Web crawl:        OK — 1 page, 0 failures, 36,782 characters, 2.32s
Final process:    SUCCESS
```

The MCP server connected and exposed both tools, but its internal tool execution
returned an authentication-service error. The router automatically used the
structured REST transport and completed search plus crawl without user action.

## 6. Known limitations carried forward

1. MCP tool execution must be re-tested before final deployment; REST currently
   provides the production-capable fallback.
2. Search relevance is not evidence quality. The returned sources still require
   source-tier classification, relevance ranking, corroboration, and human review.
3. The current stage does not yet extract claim-level quotes or map claims to
   citations.
4. The current stage has not yet run inside Streamlit Community Cloud; online
   outbound connectivity and Secrets configuration will receive a deployment
   smoke test.
5. No real enterprise-confidential information is authorized for the public MVP.

## 7. Stage decision

Stage 1 passes because the complete model -> search -> fallback -> crawl path ran
successfully with real competition services, typed outputs, safe credentials,
and repeatable offline tests.

Stage 2 may begin only after user review. Stage 2 will create the lightweight
Streamlit product shell and universal project-entry flow; it will not yet encode
the professional research SOP or generate a full industry report.
