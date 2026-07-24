# Stage 6 Acceptance — Falsifiable Future Intelligence

**Status:** Ready for user review  
**Review date:** 24 July 2026

## 1. Purpose

Predict how an industry may change without presenting forward-looking judgment
as current fact. Every forecast starts from accepted evidence and approved
current-state analysis, explains its causal mechanism, and states what should be
monitored and what would invalidate it.

## 2. Forecast outputs

- technology and product trends;
- competitive-landscape changes;
- business-model changes;
- customer-demand shifts;
- policy, capital, and value-chain effects;
- observed, announced, and inferred player moves;
- baseline, accelerated, and blocked scenarios;
- leading indicators, triggers, uncertainties, and falsification conditions;
- optional target-company exposure, without scoring or action advice.

## 3. Trend contract

Each trend records:

- category, horizon, and end year;
- forward-looking statement;
- observed signals with Evidence and Finding links;
- causal mechanism and assumptions;
- affected players;
- player moves explicitly labelled `observed`, `announced`, or `inferred`;
- competition, business-model, and customer-demand effects;
- leading indicators and monitoring sources;
- falsification conditions and uncertainties;
- supporting and counter Evidence IDs;
- accepted Industry Finding IDs;
- system-calculated confidence;
- human-review status, note, and timestamp.

## 4. Confidence calculation

The model cannot choose the final confidence score. Code calculates:

- evidence quality;
- source diversity;
- signal consistency;
- causal clarity;
- player commitment;
- forecast time distance;
- counter-evidence resilience;
- enterprise signal support, which remains `None` in General mode.

The weighted overall score is transparent and reproducible. The current MVP is
not presented as a trained machine-learning forecast.

## 5. Scenario controls

Exactly three scenarios are required:

1. baseline;
2. accelerated;
3. blocked.

Each scenario has unique ID, triggers, expected outcomes, linked trends,
Evidence and Finding IDs, leading indicators, falsification conditions, and a
qualitative `low`, `moderate`, or `high` likelihood label.

Unknown references, duplicate scenarios, past forecast end dates, or explicit
probability fields reject the output. Invalid JSON and invalid structures each
receive at most one repair attempt.

## 6. Human review gate

Reviewers accept or reject every trend and every scenario. The gate remains
blocked while any item is pending, when no trend is accepted, or when the
baseline scenario is not accepted. Approval marks Future Intelligence complete.
Company Assessment becomes ready only when the enterprise strategy path is
enabled and its strategic-intent and Enterprise Sensing gates have also passed.
General research instead continues toward a General Report without a company
score.

## 7. Methodology rules

The temporary generic baseline adds:

- `FUTURE-001`: traceable forecast chain;
- `FUTURE-002`: player-move status separation;
- `FUTURE-003`: multiple scenarios rather than a single answer;
- `FUTURE-004`: leading indicators and falsifiability;
- `FUTURE-005`: no false numerical precision.

These remain replaceable by a later Sullivan trend-forecasting SOP pack.

## 8. Verification

Automated result:

```text
38 passed
```

Tests cover unknown Finding references, deterministic confidence, scenario and
trend review gates, one invalid-JSON retry, rejection of unvalidated probability
fields, and deep Streamlit rendering from session artifacts.

Real HKGAI end-to-end result:

```text
input_evidence=5
input_findings=15
trends=3
scenarios=3
avg_confidence=74
future_rules=5
```

The live chain ran public search, crawl, evidence extraction, current Industry
Analysis, and Future Intelligence. An earlier real run returned malformed JSON;
the product now handles this safely with one structured retry and never stores
the malformed response.

Browser validation confirmed the Trend Forecast page loads without exception,
shows the correct Stage 6 label, and blocks a case project that has not completed
Evidence Matrix and Industry Analysis review.

## 9. Known limitations

1. Enterprise Sensing is not yet connected to the confidence calculation, so
   General mode leaves that component unset.
2. The confidence formula is a transparent MVP heuristic, not a calibrated
   predictive model.
3. No persistent monitoring scheduler or database exists yet.
4. Historical time-series adapters and quantitative forecasting are future
   extensions.
5. The methodology pack remains a generic baseline rather than Sullivan SOP.
6. Forecast artifacts remain in the Streamlit browser session.

## 10. Decision requested

Approve whether the trend, scenario, monitoring, confidence, and falsification
structure is suitable as the input to Stage 7 Company Scorecard.
