# Stage 3 Acceptance — SOP Research Brief and Research Planner

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Purpose

Prevent the model from jumping directly from a user question to an industry
answer. The agent must first define the research purpose, optional management
decision, and market boundary, then create an executable, reviewable research
plan under a locked methodology pack.

## 2. Methodology architecture

```text
Universal Research Core
  -> active versioned Research SOP Pack (locked)
  -> optional Industry Pack
  -> optional company-private inputs
  -> structured artifact validation
  -> named human approval gate
```

The active SOP records its ID, display name, version, SHA-256 content hash,
applicable rule IDs, and deterministic compliance checks. External web content
cannot override this layer.

The current pack is explicitly labelled as a temporary generic baseline. It is
not presented as a third-party methodology. A future professional SOP pack replaces the
baseline while keeping the same schemas, service interface, UI, and audit trail.

## 3. Research Brief capability

- real HKGAI Modelhub call;
- research-purpose-first framing with optional business-decision context;
- product, customer, geography, value-chain, and time boundaries;
- inclusions and exclusions;
- key research questions;
- information gaps;
- hypotheses;
- clarification questions;
- confidence note;
- full user editing;
- human confirmation before planning.

Changing the original project inputs invalidates the previous Brief and Plan so
stale research logic cannot silently survive a scope change.

## 4. Research Planner capability

- real HKGAI Modelhub call;
- task sequence and dependencies;
- task questions and hypotheses;
- information needs;
- preferred source types;
- ready-to-use search queries;
- deliverables;
- evidence standards;
- mandatory counter-evidence;
- validation gates;
- unresolved gaps;
- human approval before evidence collection.

## 5. SOP enforcement

The baseline currently enforces:

- 5–12 key questions;
- at least 3 hypotheses;
- explicit inclusions and exclusions;
- 5–10 research tasks;
- at least 2 human-review gates;
- unique task IDs;
- non-empty source, search, evidence, and validation fields;
- counter-evidence on every task.

When output fails, the system does not relax the rules. It returns the violation
to the same model for one complete repair attempt. A second failure is exposed to
the user and the workflow remains blocked.

## 6. Verification

Offline result:

```text
23 passed
```

Live service result:

```text
Brief: OK — 9 questions, 4 hypotheses,
SOP generic_research_baseline@1.0.0
Plan:  OK — 8 tasks, 3 review gates, SOP locked=True
```

Live browser result:

- loaded the China molecular-diagnostics case demonstration;
- generated an editable AI Research Brief through HKGAI;
- displayed SOP lock and trace metadata;
- confirmed the Brief through the human gate;
- generated a Research Plan through HKGAI;
- displayed tasks, source strategy, search queries, evidence rules, gaps, and
  review gates;
- approved the plan;
- advanced `Research Planning` to `Completed` and `Evidence Collection` to
  `Ready`;
- no browser console error.

## 7. Known limitations

1. The active pack is not yet a specialized methodology.
2. Qualitative SOP compliance still combines prompting, structural enforcement,
   and human review; later evaluation sets should test method quality against
   approved professional examples.
3. Evidence search has not started in this stage.
4. Generated artifacts currently remain in the browser session rather than a
   persistent database.
5. Long thinking calls need progress and timeout tuning before public deployment.

## 8. Decision requested

Approve whether the current Brief and Planner product flow is suitable as the
stable container for the future professional SOP pack. After approval, the rapid
end-to-end build can proceed to evidence collection and evidence QA.
