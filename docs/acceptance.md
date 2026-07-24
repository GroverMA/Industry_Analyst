# MVP Acceptance Criteria

## 1. Universal-industry gate

The MVP fails if the application is hard-coded to molecular diagnostics.

Acceptance requires:

- a user can create a project using any free-text industry name;
- the workflow runs when no Industry Pack is installed;
- the system labels this path as `general research mode`;
- a user can optionally select a matching Industry Pack;
- removing or replacing a pack does not require changing Research Core code;
- company-private data remains separate from the selected pack;
- molecular-diagnostics terms do not appear in an unrelated project unless supplied by evidence or user input.

Planned cross-industry smoke cases:

1. China molecular diagnostics — deep Industry Pack mode;
2. industrial robotics — general research mode;
3. enterprise SaaS — general research mode.

## 2. Research-process gate

- The agent cannot produce a final report before a Research Brief and market definition exist.
- Research Setup records the research objective, optional business decision, geography, time horizon, inclusions, exclusions, and unresolved ambiguities.
- A research plan contains tasks, hypotheses, information gaps, validation nodes, and human-confirmation status.
- Rejected market definitions return to Research Setup instead of silently continuing.

## 3. Enterprise-sensing gate

- Enterprise Sensing is an optional enhancement, never a prerequisite for report generation.
- When no private input is supplied, the workflow continues using public evidence, the selected Industry Pack, and model analysis.
- A user can submit a first-hand observation.
- An observation records contributor role, date, scope, type, confidence, and usage permission.
- A user can attach at least PDF, DOCX, TXT/Markdown, and simple spreadsheet files.
- Private inputs are visibly labeled and do not become public evidence.
- Unverified observations are treated as signals, not facts.

## 4. Evidence gate

- Each material claim links to one or more evidence records or is marked as unsupported.
- Evidence records capture source, publisher/contributor, date, scope, excerpt, type, and reliability.
- Claims are classified as `fact`, `view`, `inference`, or `forecast`.
- Conflicting evidence remains visible.
- The system checks source freshness and market-definition consistency.

## 5. Analysis gate

- Competitive Landscape distinguishes direct, indirect, potential, substitute, benchmark, and value-chain players.
- Market Drivers include mechanism, affected actor, direction, timing, evidence, counter-evidence, and leading indicator.
- Future Intelligence includes observed signals, causal mechanism, baseline/accelerated/blocked scenarios, counter-evidence, leading indicators, and falsification conditions.

## 6. Company-strategy gate

- Scores are relative to an explicit benchmark and decision context.
- Each score displays evidence, confidence, and data completeness.
- The system distinguishes market attractiveness from company strategic fit.
- Strategic options include dependencies, risks, and reasons for ranking.
- Action Plan items contain action, rationale, priority, owner, timing, leading metric, outcome metric, risk, and stop condition.

## 7. Human-review gate

- Critical evidence can be accepted, rejected, or returned for more research.
- Review records the reviewer role, decision, reason, and timestamp.
- The reviewer can challenge logic, request counter-evidence, or lower confidence.
- High-impact recommendations cannot become approved decisions without a human gate.

## 8. User-experience gate

The lightweight web application exposes:

1. Project Home;
2. Research Setup;
3. Industry Overview;
4. Competitive Landscape;
5. Market Drivers;
6. Future Intelligence;
7. Company Strategy;
8. Decision Report;
9. persistent Enterprise Sensing access.

Users can inspect evidence, reasoning, counter-evidence, and review status from analytical outputs.

## 9. Output gate

- Decision Report contains management conclusion, industry findings, company assessment, strategic options, Action Plan, risks, evidence matrix, and limitations.
- Report export works in Markdown and JSON.
- Missing or low-confidence information is visible rather than hidden.

## 10. Evaluation gate

For the same golden-case question, compare:

- a single-prompt general-model report;
- the complete Industry Analyst OS workflow.

Score both on:

- market-definition quality;
- evidence traceability;
- competitor coverage;
- causal-analysis depth;
- forecast testability;
- company relevance;
- Action Plan executability;
- explicit uncertainty and accountability.

The MVP passes when the workflow result is materially more traceable, reviewable, and decision-ready than the single-prompt baseline, even if some domain conclusions still require expert validation.
