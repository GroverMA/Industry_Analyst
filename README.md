# Trident

Trident is a lightweight, evidence-first enterprise industry research and strategic decision intelligence agent. It turns professional research methods into two interoperable paths: build from the research question or review a complete draft first. Both paths share the same project data, evidence base, analytical logic, report versions, and export formats.

## Product principle

The product is industry-agnostic by default. Users may start a project for any industry. Industry-specific expertise is added through optional `Industry Packs`; company-specific knowledge remains in an isolated private workspace.

The first high-confidence case demonstration covers the China molecular diagnostics industry. It is an evaluation baseline, not a hard-coded product boundary.

## Three knowledge layers

1. **Public evidence** — web pages, policies, filings, reports, news, patents, and tenders.
2. **Industry Pack** — terminology, taxonomy, metrics, competitor dimensions, analytical methods, and consultant SOPs.
3. **Company private workspace (optional for a General Report; required for company advice)** — internal documents, sales feedback, customer interviews, channel observations, operating data, and expert input. The agent can complete a general report when this layer is absent, but it will not invent a Company Scorecard or Action Plan.

## MVP workflow

1. Create a research project for any industry and choose Quick Report or Analyst Workspace.
2. Define the mandatory research objective, market boundary, and optional business decision.
3. Generate the research design and execute public web research on one Research Studio page.
4. Pass Gate 1: the user confirms source authenticity and evidence usability.
5. Analyze industry structure, competitors, drivers, commercial logic, trends, and scenarios.
6. Pass Gate 2: the user confirms which findings and forecasts enter the report.
7. Preview and download the human-reviewed General Report as editable Word or paginated PDF.
8. Optionally add enterprise sensing, assess company fit, and develop an Action Plan.

## Case demonstration

The reference case evaluates how a fictional Chinese IVD company, GeneMatrix Diagnostics (基矩诊断), should allocate limited resources across PCR, digital PCR, NGS, and integrated molecular diagnostic solutions between 2026 and 2030.

See [docs/golden_case.md](docs/golden_case.md).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The application does not call the model or search service merely by loading a
page. Put local competition credentials in `.env` only when running integration
checks; use Streamlit Secrets for the later online deployment.

## Deploy online

The production target is Streamlit Community Cloud with `app.py` as the
entrypoint and Python 3.12. Runtime credentials belong in Community Cloud
Secrets and are never committed. See [DEPLOYMENT.md](DEPLOYMENT.md) and
[.streamlit/secrets.example.toml](.streamlit/secrets.example.toml).

## Current stage

Stage 7B — Company Scorecard, strategy-bound Action Plan, and Enterprise
Decision Report — implemented and awaiting user acceptance.

The enterprise path now converts accepted external evidence, accepted
first-party enterprise inputs, approved industry analysis, and approved Future
Intelligence into a six-dimension Company Scorecard. Every scored dimension is
relative to an explicit benchmark and shows public Evidence IDs, Enterprise
Evidence IDs, system-calculated score, confidence, and data completeness.
Missing company evidence produces an unscored dimension rather than a neutral
placeholder. A human must accept or reject every dimension before the scorecard
can advance.

The Action Plan is generated only after the scorecard is human-confirmed. Every
action is anchored to the user's enterprise strategy objective and contains a
priority, accountable owner role, timing, resources, dependencies, leading KPI,
outcome KPI, risks, mitigations, stop conditions, uncertainty, and trace IDs.
After a second human gate, the app composes a downloadable Enterprise Decision
Report that retains the complete General Industry Report as its appendix.

Enterprise Sensing includes a clearly labelled fictitious and redacted demo
pack so judges can run the enterprise pathway without real confidential data.
Real enterprise inputs remain optional for a General Report and mandatory for
company-specific scoring or recommendations. Any upstream evidence, company,
strategy, analysis, or forecast change invalidates downstream company advice.

Stage 7A.3 remains the single-page Prompt-to-Report foundation.

Quick Report and Analyst Workspace are two views over the same research state.
The default Research Studio first calls the model to interpret the original
Prompt, pauses for editable market-scope alignment, runs public web research,
supports batch Evidence review, generates current analysis and future
intelligence, pauses for report-content review, checks every must-answer
question, and then produces a downloadable Word and PDF report. The final
writing pass converts approved facts, judgments, trends, and scenarios into
formal, complete analytical paragraphs without adding unsupported claims.
Analyst
Workspace embeds enterprise strategy and first-party sensing status without
forking the public research workflow.

The sidebar keeps full browser-local project snapshots in IndexedDB. It separates
in-progress and completed studies, shows each project's progress and current
research node, restores the exact workflow state, supports project search, and
lets users create folders and move projects between them. This lightweight MVP
persists after refresh on the same browser and device; authenticated cross-device
history remains a later cloud-database extension.

Stage 7A remains the enterprise strategy eligibility foundation.

The product now has two explicit paths. General Research can complete an
industry and future-trend report without company data. Company Strategy Research
requires a target company, a user-authored strategic intent, at least one
human-accepted Enterprise Evidence item, and explicit data-use confirmation.
Company Scorecard and Action Plan remain locked until these conditions pass.

The strategic intent is stored as a reviewed snapshot and is the primary input
to the later Action Plan. If the company or intent changes, prior Enterprise
Sensing confirmation becomes invalid. The public demo accepts manual inputs and
TXT, Markdown, CSV, PDF, DOCX, or XLSX files, but blocks accepted confidential
or restricted content from confirmation. Real secrets require private
deployment and access controls.

Stage 6 remains the future-intelligence foundation.

After current Industry Analysis is approved, the agent can now generate
evidence-linked future trends, observed signals, causal mechanisms, player-move
inferences, leading indicators, falsification conditions, and three qualitative
scenarios: baseline, accelerated, and blocked. Every trend must cite accepted
Evidence IDs and accepted Industry Finding IDs.

Forecast confidence is calculated by code rather than copied from model prose.
The score combines evidence quality, source diversity, signal consistency,
causal clarity, player commitment, forecast distance, and counter-evidence
resilience. Enterprise signal support remains explicitly unset in General mode.
Without a validated dataset and statistical model, precise probability fields
are rejected.

Stage 5 remains the current-state analysis foundation.

After the Evidence Matrix is approved, HKGAI can now generate five strictly
current-state modules: market definition and value chain, market status and
structure, competitors and comparables, drivers and constraints, and current
commercial logic. Every finding cites human-accepted Evidence IDs and declares
its type, mechanism, confidence, uncertainty, scope, and failure boundary.
Competitor findings must explain whether a player is direct, indirect,
benchmark, or adjacent and state the comparison basis. Users accept or reject
each finding before the current Industry Analysis can advance to Future
Intelligence.

Future trends, scenarios, player-move inference, business-model shifts, leading
indicators, and falsification conditions remain separate from current-state
claims. This prevents current facts and forward-looking judgments from being
presented as the same kind of claim.

Stage 4 remains the evidence foundation.

An approved Research Plan can now launch real Agenthub searches task by task or
for all pending tasks. The agent routes MCP first and falls back to structured
REST, deduplicates candidate URLs, assigns transparent source tiers, crawls a
bounded set of high-value pages, and uses HKGAI Modelhub to extract facts, data,
source viewpoints, inferences, and source forecasts. Exact-quote checks,
research-scope checks, conflict flags, information gaps, quality scores, and
human accept/reject decisions are recorded in an Evidence Matrix. A model output
never becomes verified evidence automatically.

The stage uses bounded defaults of two searches, five results per search, and
two crawled pages per task. A crawl cache avoids repeated network calls within
the app process. The evidence gate remains blocked until every Research Plan
task has run and has at least one human-accepted evidence item.

Stage 3 remains the methodology foundation. The application calls HKGAI
Modelhub to transform project inputs into an editable market definition,
research questions, hypotheses, information gaps, and clarification questions.

After human approval, it generates an executable
research plan with tasks, source priorities, search queries, evidence standards,
counter-evidence requirements, dependencies, and review gates.

The active methodology pack is versioned, fingerprinted, injected as a locked
instruction layer, and recorded on every generated artifact. Invalid model
output is rejected and receives one SOP-preserving repair attempt. The bundled
generic baseline exists only to run the workflow now; a future professional SOP pack
will replace it without changing the Research Core or UI workflow.

The Stage 2 shell remains industry-neutral: users can create projects for any
industry, while China molecular diagnostics is an optional case demonstration
with an Industry Pack label.

Stage 1 remains the provider foundation: HKGAI Modelhub, MCP search/crawl,
structured REST fallback, typed candidate evidence, safe runtime configuration,
and a successful real model -> search -> fallback -> crawl validation.

See [docs/hkgai_capability_validation.md](docs/hkgai_capability_validation.md).
See [docs/stage_1_acceptance.md](docs/stage_1_acceptance.md).
See [docs/stage_2_acceptance.md](docs/stage_2_acceptance.md).
See [docs/stage_3_acceptance.md](docs/stage_3_acceptance.md).
See [docs/stage_4_acceptance.md](docs/stage_4_acceptance.md).
See [docs/stage_5_acceptance.md](docs/stage_5_acceptance.md).
See [docs/stage_6_acceptance.md](docs/stage_6_acceptance.md).
See [docs/stage_7a_acceptance.md](docs/stage_7a_acceptance.md).
See [docs/stage_7a_2_acceptance.md](docs/stage_7a_2_acceptance.md).
See [docs/stage_7b_acceptance.md](docs/stage_7b_acceptance.md).
See [docs/research_sop_input_template.md](docs/research_sop_input_template.md).
