# Stage 4 Acceptance — Evidence Collection and Evidence QA

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Purpose

Turn an approved Research Plan into a traceable body of evidence without
treating search results or model prose as facts. Stage 4 stops at evidence
collection and quality review; it does not yet write industry conclusions,
forecasts, company scores, or action plans.

## 2. Runtime chain

```text
Approved Research Plan
  -> task search queries (bounded)
  -> SearchRouter (MCP first, structured REST fallback)
  -> URL deduplication and source-tier classification
  -> high-value page selection and crawling
  -> HKGAI structured evidence extraction
  -> deterministic quote, scope, reliability, and conflict checks
  -> Candidate Evidence
  -> Human accept / reject
  -> Evidence Matrix gate
```

The page performs no external call merely by loading. Search starts only when a
user selects a task or explicitly runs all pending tasks.

## 3. Evidence boundaries

The implementation separates three states:

1. a search result is a **candidate source**;
2. a model-extracted statement is **candidate evidence**;
3. only an explicitly accepted item is **verified evidence** for the later
   workflow.

Each evidence item records task ID, source ID, evidence type, statement, exact
supporting excerpt, date, geographic and market scope, support/challenge role,
model confidence, deterministic QA score, flags, review status, reviewer note,
and review timestamp.

## 4. Default source tiers

- **A:** government, regulator, exchange, formal statistics, and statutory
  disclosures;
- **B:** academic, standards, formal international institutions, and similar
  accountable sources;
- **C:** professional media, consulting or research organizations, company
  websites, and credible industry platforms;
- **D:** aggregators, encyclopedias, self-media, and sources without a stable
  accountable publisher.

The classifier is deliberately transparent and conservative. It is a baseline,
not a claim that domain names prove truth. Future industry packs can add or
override source rules.

## 5. Search and cost controls

Default per task:

- maximum 2 Research Plan queries;
- maximum 5 results retained per query;
- maximum 2 pages crawled;
- domain diversity preferred during page selection;
- URLs deduplicated within each run;
- crawled pages cached within the running app process;
- maximum 7,000 characters of each page sent to the model;
- maximum 10 evidence candidates returned per task;
- one structure-preserving extraction repair attempt.

Users can run one task first, run all pending tasks, or supply one replacement
query for a focused rerun.

## 6. Automatic QA and human gate

Automatic statuses include:

- Needs Review;
- Conflicted;
- Out of Scope;
- Low Reliability;
- Unsupported;
- Accepted;
- Rejected.

An excerpt that cannot be found in the crawled page is marked `Unsupported`.
Risk-flagged evidence can only be manually accepted after the reviewer records
an override reason. The stage gate requires every planned task to have run and
to contain at least one human-accepted evidence item. Remaining gaps and
conflicts stay visible rather than being silently resolved.

## 7. Verification

Automated result:

```text
27 passed
```

Real service result:

```text
queries=1
sources=5
crawled=2
evidence_candidates=10
transports=['rest']
```

The live validation attempted MCP first, automatically used structured REST
after the provider-side MCP execution issue, crawled real pages, and invoked the
real HKGAI model for structured extraction.

Live browser result:

- generated and approved a real Research Brief and eight-task Research Plan;
- opened the Evidence workspace;
- ran a focused real search for task T01;
- displayed 5 sources, 10 candidates, information gaps, source links, QA states,
  and the Evidence Matrix;
- accepted one item with a reviewer note;
- updated Verified Evidence from 0 to 1;
- kept the workflow blocked because T02–T08 had not yet run.

## 8. Known limitations

1. Public search quality depends on the competition search service and query
   quality; low-quality or corrupted pages remain visible as candidates but are
   not auto-accepted.
2. Publication date extraction is not yet independently resolved from page
   metadata.
3. Corroboration currently flags model-identified conflicts but does not yet
   require two independent accepted sources for every material claim.
4. Evidence remains in the Streamlit browser session rather than a persistent
   database.
5. The active research methodology is still the temporary generic baseline,
   pending the Sullivan SOP pack.

## 9. Decision requested

Approve whether this candidate-source → candidate-evidence → verified-evidence
workflow is the correct foundation for Stage 5 Industry Analysis. The next
stage should use only human-accepted evidence and explicitly preserve gaps,
conflicts, and inference boundaries.
