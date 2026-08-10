# Stage 7A Acceptance — Enterprise Strategy Eligibility

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Purpose

Create a hard boundary between a general industry report and company-specific
advice. The agent may analyze any industry without private company data, but it
must not invent a company's strategy, capabilities, score, or action plan.

## 2. Two product paths

### General industry research

- mandatory: industry, region, time range, and research objective;
- optional: target company and business decision context;
- Enterprise Sensing may be skipped;
- outputs: current industry analysis, competitors, drivers and constraints,
  future trends, scenarios, Evidence Matrix, and General Report;
- Company Scorecard and Action Plan are marked `Not Applicable`.

### Company strategy research

- mandatory: target company;
- mandatory: explicit company strategic intent;
- mandatory: at least one human-accepted Enterprise Evidence item;
- mandatory: project-only model-processing consent and public-demo data
  acknowledgement;
- Company Scorecard remains locked until Future Intelligence is also approved;
- Action Plan remains locked until Company Scorecard is completed and reviewed.

## 3. Strategic-intent contract

The company strategic intent is a first-class project input and the primary
constraint for the later Action Plan. It should state the desired strategic
position, protected boundaries, time horizon, and relevant resource or risk
constraints.

Industry evidence and future scenarios may challenge or refine execution, but
they may not silently replace the company's stated intent. Every later action
must declare how it supports that intent. If the target company or strategic
intent changes, the Enterprise Sensing snapshot becomes invalid and must be
reviewed again.

## 4. Enterprise Evidence contract

Each input records:

- Enterprise Evidence ID;
- title, category, and statement type;
- content and source owner;
- observation date;
- relationship to strategic intent;
- sensitivity level;
- manual or file input method;
- file name and SHA-256 fingerprint where applicable;
- human accept/reject status, note, and timestamp;
- project-only permission.

Statement types distinguish facts, observations, viewpoints, hypotheses,
strategic intent, and mixed documents. Files support TXT, Markdown, CSV, PDF,
DOCX, and XLSX with a 300 MB per-file upload limit and a 50,000-character extraction limit.

## 5. Public-demo safety boundary

The UI explicitly requires redacted or simulated content. An artifact containing
accepted unredacted `internal`, `confidential`, or `restricted` material cannot pass the public-demo
confirmation gate. Real company secrets require private deployment, access
control, retention policy, and audit capability.

Enterprise inputs stay separate from public Evidence Matrix items and do not
automatically become shared Industry Pack knowledge.

## 6. User-visible linkage

- Project Home and Research Brief expose the enterprise strategy-path switch.
- The strategy objective is visibly labelled as the anchor for Action Plan.
- Enterprise Sensing explains that it is optional for General Report but
  mandatory for Company Scorecard and Action Plan.
- Company Scorecard shows all missing prerequisites instead of placeholder
  scores.
- Action Plan displays the locked strategic objective and refuses to produce
  recommendations while prerequisites are incomplete.
- Decision Report conditionally includes company scoring and action sections
  only for the company strategy path.

## 7. Verification

Automated result:

```text
48 passed
```

Tests cover strategy-path validation, strategy snapshot invalidation, accepted
Enterprise Evidence, consent gates, public-demo sensitivity rejection, text and
CSV extraction, `Not Applicable` completion logic, Golden Case configuration,
and Streamlit page rendering. Unredacted `internal` content is blocked along
with `confidential` and `restricted` content.

## 8. Scope boundary

This stage establishes eligibility, provenance, permissions, and module
linkage. It does not yet generate Company Scorecard values or Action Plan
recommendations. Those are the next implementation stages and must consume the
approved strategic intent snapshot rather than free-form model assumptions.

## 9. Decision requested

Approve whether the two-path design, required enterprise inputs, strategic
intent lock, and public-demo data boundary are suitable before Company
Scorecard generation is implemented.
