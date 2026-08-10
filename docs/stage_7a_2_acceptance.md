# Stage 7A.3 Acceptance — Prompt-to-Report Research Studio

**Status:** Ready for user review  
**Review date:** 25 July 2026

## 1. Purpose

Move from a user's original research prompt to a downloadable industry report
through one continuous, resumable page. Quick Report and Analyst Workspace use
the same `ProjectState`, confirmed market scope, Research Plan, Evidence Matrix,
analysis, forecast, report, and optional enterprise inputs.

## 2. Unified modes

- Quick Report exposes the shortest complete research path.
- Analyst Workspace keeps that same path and embeds company target, strategic
  objective, Enterprise Sensing status, quick first-party observation entry,
  and Scorecard/Action Plan eligibility.
- Detailed sidebar pages inspect or edit the same artifacts; they no longer
  represent a separate workflow.

## 3. Three human gates

### Gate 0 — Prompt interpretation and market scope

The model semantically interprets the original prompt and generates requested
topics, must-answer questions, terminology mappings, ambiguities, inclusions,
exclusions, adjacent markets, market-sizing basis, and competitor definition.
The user can edit every material field. Only a confirmed brief can generate a
Research Plan, analysis, forecast, or report.

The Gate 0 submit button remains interactive while the Streamlit form is being
edited. Confirmation is validated on submit, avoiding the stale disabled-button
state caused by form widgets not rerunning until submission.

### Gate 1 — Evidence authenticity and usability

The user sees source URL, excerpt, evidence statement, type, source tier, and QA
score. Batch actions support system-recommended selection, select all, and clear
all. Gate 1 is persisted before model analysis begins, so a later model failure
does not repeat search or evidence review.

### Gate 2 — Report content

The user selects the findings, trends, and scenarios that may enter the report.
Trend-to-finding and scenario-to-trend dependencies must remain closed. At least
one trend and the baseline scenario must be accepted.

## 4. Continuous pipeline

```text
Original prompt
→ AI prompt interpretation
→ Gate 0 market-scope alignment
→ confirmed Research Brief and Research Plan
→ public web research
→ Gate 1
→ industry analysis
→ future intelligence
→ Gate 2
→ Prompt Coverage Check
→ general report
```

The initial action only interprets the prompt. Web search starts after Gate 0.
State is saved after scope confirmation, after each evidence task, immediately
after Gate 1, after current analysis, and after future intelligence.

## 5. Semantic factor handling and recovery

Development conditions, growth drivers, enabling conditions, constraints,
challenges, and key variables are interpreted semantically rather than by user
keyword. The internal taxonomy supports `driver`, `constraint`,
`enabling_condition`, `mixed`, and `conditional`, with a separate impact
direction.

Formatting aliases are normalized. After a targeted repair, an individual
factor that still cannot be classified is excluded and recorded as an evidence
gap instead of failing all five analysis modules. Users see a retry action, not
Pydantic, JSON, `force_type`, or framework tracebacks.

## 6. Prompt-grounded report

The report contains Original Prompt Coverage, Executive Summary, confirmed
market definition, accepted current-industry modules, Future Intelligence,
scenarios, limitations, Evidence Matrix, and the three-gate review record.

The language model assesses question coverage using only accepted material. A
deterministic validator rejects unknown Evidence, Finding, or Trend IDs. Missing
answers are shown as partial coverage or explicit evidence gaps. Markdown and
structured report JSON are available in Research Studio and Decision Report.

## 7. Enterprise extension

General reports remain available without enterprise inputs. Analyst Workspace
shows the target company, strategic objective, first-party input counts, and
the exact conditions for Company Scorecard and Action Plan. Manual observations
can be added in place; document upload and full review remain in Enterprise
Sensing. Enterprise information does not silently enter the public Evidence
Matrix.

## 8. Memory and compatibility

Streamlit session state provides working memory. A complete
`.industry-project.json` snapshot can be downloaded and restored. New fields
have backward-compatible defaults for older snapshots. Evidence objects cross
a plain-JSON validation boundary, and the cached Evidence service is versioned
to prevent stale hot-reload class or workflow rules.

## 9. Verification

Automated result:

```text
58 passed
```

Coverage includes Gate 0 enforcement, semantic factor aliases, unclassified
factor degradation, Evidence batch controls, mode persistence, project snapshot
round-trip, Future Intelligence, Prompt Coverage ID validation, and Streamlit
rendering.

Real HKGAI browser verification confirmed:

- the AI Prompt Analysis entry calls the configured model;
- all eight progress cards render as cards rather than code;
- Analyst Workspace embeds enterprise strategy and downstream eligibility;
- Gate 0 exposes original prompt, interpreted objective, must-answer questions,
  market-sizing basis, competitor definition, inclusions, and exclusions;
- no raw traceback appeared.

Earlier Agenthub integration validation remains:

```text
queries=1
sources=5
crawled=1
evidence_candidates=3
transports=['rest']
```

## 10. Current limitations

1. General report export is Markdown and JSON; PDF/DOCX is not yet implemented.
2. Cross-device persistence requires later authentication and tenant-isolated
   PostgreSQL or Supabase storage.
3. Full multi-task live research may take several minutes.
4. The baseline SOP remains active until a versioned professional SOP pack is supplied.
5. Company Scorecard and Action Plan are eligibility shells for the next stage.

## 11. Decision requested

Approve the two-mode, three-gate Prompt-to-Report flow before implementing the
scored Company Scorecard and generated Action Plan.
