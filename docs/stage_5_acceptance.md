# Stage 5 Acceptance — Evidence-Grounded Industry Analysis

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Purpose

Convert the approved Evidence Matrix into a current-state industry analysis
without allowing model memory, unaccepted sources, or unsupported prose to
silently enter the result.

This stage deliberately excludes future-trend prediction, scenarios,
probabilities, resource-allocation recommendations, company scoring, and action
plans. Those belong to later governed stages.

## 2. Five current-state modules

1. market definition and value chain;
2. market status and structure;
3. competitors and comparable companies;
4. market drivers and constraints;
5. current commercial logic.

Target-company implications are optional and appear only when a target company
was provided. They are explicitly labelled as preliminary implications rather
than a score or recommendation.

## 3. Finding contract

Every finding records:

- subject;
- finding type: fact synthesis, source viewpoint, analyst inference, or
  commercial judgment;
- statement;
- explanatory mechanism;
- supporting accepted Evidence IDs;
- counter-evidence IDs;
- comparison dimensions;
- confidence;
- scope;
- uncertainty;
- boundary or failure condition;
- human-review status, note, and timestamp.

The analysis artifact also records cross-module conflicts, overall evidence
limitations, evidence gaps, rejected questions, methodology version, content
hash, and every Evidence ID made available to the model.

## 4. Deterministic controls

- the Evidence Matrix must be human approved;
- only `Accepted` evidence enters the model context;
- rejected or unreviewed evidence is excluded;
- every finding must cite at least one allowed Evidence ID;
- unknown or unaccepted Evidence IDs reject the entire output;
- all five module IDs must appear exactly once;
- an empty module must state its evidence gaps;
- competitor findings must specify relationship type and comparison basis;
- driver/constraint findings must specify force type;
- no target company means no invented company implications;
- invalid output receives one complete repair attempt without relaxing rules.

## 5. Human review gate

The web workspace shows each finding together with its Evidence links,
mechanism, confidence, uncertainty, and boundary condition. The reviewer can
accept or reject every finding and record a reason.

The gate remains blocked while any finding is awaiting review. It also requires
at least one accepted industry finding. When approved, `Industry Analysis`
becomes `Completed` and `Future Intelligence` becomes `Ready`.

## 6. Methodology pack

The temporary generic baseline now adds four explicit analysis rules:

- `ANALYSIS-001`: use accepted evidence only;
- `ANALYSIS-002`: separate facts, viewpoints, inference, and judgment;
- `ANALYSIS-003`: explain competitor and comparable-company relationships;
- `ANALYSIS-004`: separate current analysis from future prediction.

These are stable placeholders for a future professional analysis SOP pack. The
schema, services, audit trail, and UI remain reusable when the pack is replaced.

## 7. Verification

Automated result:

```text
31 passed
```

The test suite verifies that rejected evidence is absent from model context,
unknown Evidence IDs fail after one repair attempt, human review controls the
analysis gate, and a session containing evidence plus analysis artifacts renders
the deep Streamlit workspace without exceptions.

Real HKGAI chain result:

```text
accepted_evidence=5
modules=5
findings=12
empty_modules=0
analysis_rules=4
```

The live run performed real public search, crawl, evidence extraction, human-
accepted evidence simulation for validation, and a real HKGAI current-state
industry analysis. No credentials or page bodies were printed.

## 8. Known limitations

1. Analytical depth remains bounded by the accepted evidence; missing evidence
   is surfaced rather than filled from model memory.
2. At most 60 highest-QA accepted evidence items are included in one MVP
   analysis call.
3. The active methodology is still a generic baseline, not a specialized SOP.
4. Artifacts remain in the Streamlit session rather than a persistent database.
5. Competitor financial normalization, market-sizing calculations, and
   quantitative reconciliation require later specialized methods and datasets.
6. Future trends are intentionally not generated in this stage.

## 9. Decision requested

Approve whether the five current-state modules and finding-level human review
form the correct input boundary for Stage 6 Future Intelligence.
