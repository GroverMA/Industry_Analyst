# Product Brief

## 1. Product

**Name:** Industry Analyst OS  
**Form:** Lightweight local-first web application  
**Positioning:** An evidence-first AI industry research and strategic decision agent that combines a reusable research operating system, optional industry knowledge packs, and isolated enterprise sensing inputs.

## 2. Problem

General-purpose AI can search, summarize, organize, and write, but it does not automatically possess professional research discipline. Reliable industry research requires:

- problem definition;
- market boundary control;
- task decomposition;
- explicit evidence requirements;
- validation gates;
- separation of fact, view, inference, and forecast;
- counter-evidence and falsification conditions;
- commercial judgment;
- named responsibility and human approval.

Enterprises also hold first-hand market signals that public research cannot reproduce. These signals are usually fragmented across sales, customer service, channels, product teams, interviews, and internal documents.

## 3. Product promise

Industry Analyst OS connects external market evidence with a company's own observations and capabilities to answer:

1. What is happening in the industry?
2. Why is it happening?
3. How might competition, business models, and customer needs change?
4. What does the change mean for this company?
5. What strategic options are available?
6. What should the company do, who owns it, and how will the decision be tested?

## 4. Target users

Primary MVP users:

- enterprise strategy leaders;
- CEOs and management teams;
- business development and corporate investment teams.

Future users:

- product and competitive-intelligence teams;
- consulting and market-research firms;
- PE, VC, and industrial funds.

## 5. Universal product architecture

### 5.1 Research Core

The following capabilities must work without an Industry Pack:

- accept a free-text industry or market;
- clarify the research objective and any optional business decision;
- propose and confirm a market definition;
- create a research plan;
- store and classify evidence;
- discover and compare companies;
- analyze drivers and constraints;
- form future hypotheses and scenarios;
- assess a company using configurable dimensions;
- generate strategic options and action plans;
- record review, confidence, ownership, and approval.

### 5.2 Industry Pack

An optional Industry Pack improves domain accuracy without changing core application code. A pack may contain:

- industry name, aliases, and exclusions;
- taxonomy and value-chain structure;
- specialist terminology;
- key metrics and units;
- competitor-discovery dimensions;
- source preferences;
- market-sizing logic;
- driver and trend frameworks;
- company-assessment dimensions;
- consultant SOPs and review questions;
- golden examples and evaluation cases.

If no matching pack exists, the system must continue in `general research mode` and visibly lower confidence or request expert input where domain knowledge is missing.

### 5.3 Company Private Workspace

Each company/project can contribute:

- internal files;
- first-hand observations;
- customer and channel feedback;
- expert views;
- company capabilities and constraints;
- management assumptions;
- action-plan feedback and outcomes.

Private material must never become shared Industry Pack content automatically.

## 6. User-facing modules

1. **Project Home** — create, select, and monitor projects.
2. **Research Setup** — decision goal, market boundary, research plan, and confirmation gate.
3. **Industry Overview** — current state, industry chain, value chain, and evidence.
4. **Competitive Landscape** — player map, comparison matrix, and strategic moves.
5. **Market Drivers** — causal chains, impact strength, constraints, and leading indicators.
6. **Future Intelligence** — weak signals, mechanisms, scenarios, trend probability, and falsification.
7. **Company Strategy** — relative scores, advantages, capability gaps, strategic options, and action plan.
8. **Decision Report** — management conclusion, evidence matrix, risks, approvals, and export.

A persistent **Enterprise Sensing** drawer allows file upload, observation entry, expert input, and permission selection from any relevant page.

## 7. Golden-case strategy

The China molecular diagnostics pack is the first deeply configured pack because it provides:

- a complex but definable market boundary;
- multiple technical platforms and applications;
- strong regulatory and payment influences;
- public and private evidence needs;
- meaningful competitor segmentation;
- plausible business-model and customer-demand transitions;
- company-specific resource-allocation decisions.

The demonstration should be most accurate for this case while still allowing a user to create projects in renewable energy, robotics, software, consumer goods, or any other industry.

## 8. MVP scope

### Must work

- arbitrary industry entry;
- optional Industry Pack selection;
- structured Research Brief and market definition;
- research plan and human confirmation gate;
- three-layer knowledge labels;
- enterprise observation and document input;
- evidence classification and traceability;
- industry, competitor, driver, and future-intelligence outputs;
- company assessment with confidence and data completeness;
- expert-governed Action Plan;
- human review and decision report;
- Markdown and JSON export;
- baseline comparison against a single-prompt report.

### Demonstrate through architecture, not full production implementation

- multi-pack extensibility;
- data-use permission labels;
- prediction history and backtesting records;
- execution feedback and score updates.

### Out of scope for the two-week MVP

- production multi-tenant authentication;
- enterprise SSO and full RBAC;
- large-scale crawling;
- paid proprietary databases;
- automated expert marketplace;
- model training or fine-tuning;
- complex knowledge graph infrastructure;
- mobile application;
- production private-cloud deployment;
- guaranteed precision across all industries.

## 9. Safety and decision boundaries

- No important claim may silently mix fact, view, inference, and forecast.
- Lack of evidence must produce an information gap, not invented certainty.
- Every company score requires a benchmark, evidence, confidence, and data-completeness measure.
- Every forecast requires a mechanism, counter-evidence, leading indicators, and falsification conditions.
- Every Action Plan requires an owner, timing, metric, risk, and stop condition.
- High-impact strategic recommendations require human approval.
- Private enterprise information must remain isolated from public and shared industry knowledge.
