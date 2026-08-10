# Stage 2 Acceptance — Universal Streamlit Product Shell

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Stage objective

Create the lightweight web product frame that later agent capabilities will
run inside. The shell must make the complete research journey visible, support
any industry, retain project state, and show China molecular diagnostics only as
an optional high-confidence demonstration case.

This stage intentionally does not generate industry conclusions. It establishes
the product contract and page boundaries before the professional research SOP is
encoded.

## 2. Implemented product flow

The Streamlit application exposes nine user-facing modules:

1. Project Home;
2. Research Brief;
3. Research Workflow;
4. Enterprise Sensing (optional enhancement);
5. Evidence & Analysis;
6. Trend Forecast;
7. Company Scorecard;
8. Action Plan;
9. Decision Report.

The Research Workflow page shows ten operational gates from brief definition to
human review and decision output. This separates the product navigation from the
more detailed agent workflow without hiding either from the user.

## 3. Universal-industry behaviour

- the primary entry is a free-text research form, not a molecular-diagnostics
  template;
- industry, region, target company, decision, objective, horizon, and language
  are project inputs;
- a project without a pack is visibly labelled `General Research` and
  `No Industry Pack`;
- China molecular diagnostics is a secondary `案例展示` entry;
- the case demonstration is visibly labelled `molecular_diagnostics_cn`;
- loading or removing the case demonstration does not alter the universal UI core.

The browser smoke test created and progressed a global industrial-robotics
project before loading the molecular-diagnostics case.

## 4. Product and design decisions

- minimalist white and light-transparent visual language;
- centralized color, spacing, radius, shadow, and typography tokens;
- professional desktop-first layout with responsive small-screen rules;
- sidebar preserves the complete research journey;
- no API request is triggered simply by opening a page;
- unfinished capabilities are explicitly labelled as later-stage functions;
- private enterprise inputs remain separate from public evidence and Industry
  Packs;
- high-impact recommendations display a future human-review gate.

## 5. State and validation

- typed, industry-neutral `ProjectState`;
- ten workflow statuses with completion ratio;
- immutable project updates;
- session helpers for create, retrieve, and end project;
- validated required fields on both project creation and Research Brief editing;
- JSON-backed case demonstration loader;
- project state survives navigation reruns during the browser session.

## 6. Verification result

Automated result:

```text
19 passed
```

Browser checks completed:

- empty universal home page;
- creation of a global industrial-robotics research project;
- prefilled and editable Research Brief;
- confirmation into Research Workflow;
- persistence of project data and workflow progress;
- access to all analysis and decision pages;
- Evidence page provider-configuration status without consuming an API call;
- project termination and clean return to the universal home page;
- case demonstration loading with molecular-diagnostics Industry Pack label;
- no browser console errors.

## 7. Known limitations carried forward

1. The pages are structured shells; research planning and agent execution begin
   in Stage 3.
2. Enterprise file upload, permissions, retrieval, and private deployment are not
   implemented yet.
3. Evidence records, claims, citations, conflict detection, and human-review
   actions are represented by their future page contracts only.
4. Company scoring, future scenarios, Action Plan generation, and report export
   are not active yet.
5. Streamlit Community Cloud deployment and online Secrets verification remain a
   later deployment stage.

## 8. Stage decision

Stage 2 is ready for acceptance because a reviewer can run the web product,
create a project in an unrelated industry, inspect the entire future workflow,
and load the case demonstration without confusing it with the product's universal
scope.

After user approval, Stage 3 should encode the Research Brief and Research
Planner. That stage requires the user's professional research SOP input before model
prompts and orchestration code are written.
