# Stage 7B Acceptance — Company Strategy to Action

**Status:** Implemented; ready for consolidated product review  
**Review date:** 25 July 2026

## 1. Purpose

Turn approved industry research and optional enterprise knowledge into company-
specific decisions without pretending that a general language model knows the
company. The enterprise path is an extension of the same project state used by
the General Report; it is not a disconnected second workflow.

## 2. End-to-end enterprise path

```text
User strategy objective
+ accepted redacted Enterprise Evidence
+ Gate 1 accepted public Evidence
+ Gate 2 accepted Industry Analysis and Future Intelligence
→ evidence-bound Company Scorecard draft
→ human score review and confirmation
→ strategy-bound Action Plan draft
→ human action review and confirmation
→ Enterprise Decision Report
```

The General Report remains available without any enterprise information.

## 3. Open Enterprise Sensing module

- Manual observations and uploaded TXT, Markdown, CSV, PDF, DOCX, and XLSX
  inputs remain supported.
- Inputs remain separate from public Evidence and must be accepted explicitly.
- Public demonstration blocks unredacted internal, confidential, or restricted
  inputs from final confirmation.
- A clearly labelled fictitious/redacted demo pack represents sales/channel,
  customer, R&D, finance, and management-strategy signals.
- Demo entries enter `Needs Review`; the user can review one by one or batch
  accept redacted demo inputs.

## 4. Company Scorecard

Six fixed, industry-neutral capability dimensions are used:

1. market position and competitive position;
2. product and service competitiveness;
3. commercialization, customer, and channel capability;
4. operations, economics, and delivery capability;
5. innovation and future-trend fit;
6. organization, resources, and strategy execution.

Each scored dimension requires:

- an explicit evidence-backed benchmark;
- at least one accepted public Evidence ID;
- at least one accepted Enterprise Evidence ID;
- four model judgments on a 0–5 scale: current capability, benchmark position,
  strategic fit, and future readiness;
- a system-calculated 0–100 score;
- system-calculated confidence and data completeness;
- strengths, gaps, risks, uncertainty, and a strategy-fit explanation.

If any required trace is missing, the dimension is explicitly unscored. The
model cannot submit its own final score or weights. The weighted score is only
calculated when scored dimensions cover at least 50% of total weight.

Every dimension must be accepted or rejected. Confirmation requires at least
three accepted scored dimensions covering at least 50% of total weight.

## 5. Action Plan

Action generation is locked until the Company Scorecard is confirmed. Each
action must contain:

- direct linkage to the user's stored strategy objective;
- rationale and priority;
- accountable owner role and timing;
- required resources and dependencies;
- at least one leading KPI and one outcome KPI, each with definition, target,
  timing, and named data source;
- risks, mitigations, and stop/pivot conditions;
- accepted Score Dimension, public Evidence, Enterprise Evidence, Trend, and
  optional Scenario IDs;
- system-calculated confidence and explicit uncertainty.

Unknown or unapproved IDs fail deterministic validation. Every action must be
accepted or rejected before the Action Plan can be confirmed, and at least one
action must be accepted.

## 6. Enterprise Decision Report

The report is composed only from the human-confirmed General Report,
Scorecard, and Action Plan. It contains:

- management decision frame and strategy objective;
- scorecard table, benchmarks, confidence, and completeness;
- strategic advantages, critical gaps, and cross-dimension risks;
- accepted actions, execution owners, timing, resources, KPIs, risks,
  mitigations, stop conditions, and trace IDs;
- sequencing, rejected strategic options, and portfolio risks;
- human-review timestamps and responsibility boundary;
- the complete General Industry Report as an appendix.

Markdown and structured JSON downloads are available.

## 7. Dependency and memory rules

- Changing company, strategy objective, enterprise input, public evidence,
  industry analysis, or future forecast invalidates downstream company advice.
- Changing an accepted score invalidates Action Plan and Enterprise Report.
- Changing an accepted action invalidates Enterprise Report.
- All new artifacts serialize inside the existing downloadable project
  snapshot and remain backward-compatible with snapshots that omit them.

## 8. Verification

Automated result:

```text
63 passed
```

The new tests verify system-computed scores, explicit unscored behavior,
unknown-ID rejection, score and action human gates, KPI type requirements,
enterprise-report composition, and strategy-artifact snapshot recovery.

## 9. Current limitation and professional-method input point

The active generic SOP pack does not yet contain specialized company-
assessment and Action Plan rules. Until the user supplies that pack, these
artifacts record the baseline governance rules (`PLAN-004`, `GOV-001`) as their
methodology fallback. The service and artifact contracts are already separated
from the UI, so a versioned professional SOP can replace the generic instructions without
rewriting the workflow or report pages.
