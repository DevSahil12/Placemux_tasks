# 📊 PlaceMux — Marketplace Analytics

> **Phase 2 · Week 2 · Data Analyst Track — All 5 Tasks Complete**  
> Task 1: Marketplace Data Model | Task 2: Job Supply | Task 3: Company Funnel | Task 4: Application Funnel | Task 5: Liquidity Dashboard

---

## Overview

PlaceMux is a coding-assessment and placement platform. This repository contains the complete **Data Analyst layer** — event instrumentation, metric definitions, live data pipeline, and a 7-tab analytics dashboard covering every stage of the marketplace.

| Layer | What it does |
|---|---|
| **Event tracking** | 16+ marketplace events: supply, search, view, application, verification, shortlisting |
| **Live data pipeline** | Real-time `job_posted` + `job_search_performed` + `application_submitted` stream |
| **Liquidity engine** | `liquidity_engine.py` — 14 metrics, each sourced and decision-linked, feeds the composite index |
| **Verification gate** | Every application checked against job's min_cgpa; only verified candidates can be shortlisted |
| **Dashboard** | Streamlit — 7 tabs: Liquidity, Overview, Job Supply, Company Funnel, Application Funnel, Validation, Raw Data |
| **Scalability** | Benchmarked at 10x / 50x / 100x; Liquidity Index inputs: 42ms at 100x |

---

## Quickstart

```bash
git clone https://github.com/<your-username>/placemux-analytics.git
cd placemux-analytics
pip install -r requirements.txt

python3 create_database.py              # build schema (11 tables)
python3 live_data.py seed               # seed baseline data (one-time)
python3 validate_job_supply.py          # Task 2 checks
python3 validate_company_funnel.py      # Task 3 checks
python3 validate_application_funnel.py  # Task 4 checks
python3 validate_liquidity_dashboard.py # Task 5 checks — end-to-end
streamlit run dashboard.py              # open http://localhost:8501
```

---

## Live Data

```bash
python3 live_data.py live      # rotates: job_posted / job_search / application_submitted
python3 live_data.py status    # check event stats live
```

---

## Architecture

```
Backend API
    ├─ job_posted ──────────────▶ emit_job_posted()
    │                                ├──▶ jobs
    │                                └──▶ job_supply_events          (Task 2)
    │
    ├─ student searches ────────▶ emit_job_search()
    │                                ├──▶ job_search_events          (Task 3)
    │                                └──▶ job_view_events on click   (Task 3)
    │
    └─ student applies ─────────▶ emit_application()  [verifies min_cgpa]
                                     ├──▶ applications (verified flag)
                                     └──▶ application_events         (Task 4)
                                              │
                                     emit_shortlist() — refuses if verified=0
                                              │
                              liquidity_engine.py  ── 14 metrics ── Liquidity Index
                                              │
                              dashboard.py  ── Tab 0: Liquidity Dashboard (Task 5)
```

---

## Scalability

| Scale | Liquidity Index inputs | Application funnel | Company funnel (known bottleneck) |
|---|---|---|---|
| Baseline | 0.36 ms | 0.16 ms | 3.15 ms |
| 10x | 3.82 ms | 1.62 ms | 36.87 ms |
| 50x | 21.23 ms | 9.50 ms | ~270 ms ⚠️ |
| 100x | 42.69 ms ✅ | ~20 ms ✅ | ~520–710 ms ✗ |

Company funnel bottleneck (Task 3, documented): precompute a summary table at 50x+. All other queries, including the full Liquidity Index, stay well under 100ms at 100x.

---

## Task Deliverables

| Task | Deliverable | Status |
|---|---|---|
| Task 1 | Liquidity metrics, tracking plan, data quality framework | ✅ |
| Task 2 | `job_supply_events`, `emit_job_posted()`, 5 validation checks | ✅ |
| Task 3 | `job_search_events`, `job_view_events`, fit ranking, company funnel | ✅ |
| Task 4 | `application_events`, verification gate, `emit_shortlist()`, application funnel | ✅ |
| Task 5 | `liquidity_engine.py`, Liquidity Index (82.6/100), end-to-end validation, 7-tab dashboard | ✅ |

### Task 5 Self-Check (Section 11)
- *Liquidity dashboard working live?* Yes — Tab 0, Liquidity Index 82.6/100 [HEALTHY], all 14 metrics sourced and explainable.
- *Company posts → student applies → company shortlists end-to-end?* Yes — 300 posted → 1,103 views → 1,503 applied → 1,049 verified → 486 shortlisted. Full funnel in Tab 0.
- *What happens to a student below the threshold?* `application_rejected_unverified` event fires; `verified=0` set; `emit_shortlist()` refuses; shortlist integrity = 100%.
- *How fast is search?* p95 latency: 59ms. Liquidity Index inputs query: 42ms at 100x.

---

## Files

```
placemux-analytics/
├── create_database.py              # 11-table schema
├── live_data.py                    # Live event pipeline
├── liquidity_engine.py             # Task 5: 14 metrics + Liquidity Index
├── validate_job_supply.py          # Task 2 validation
├── validate_company_funnel.py      # Task 3 validation
├── validate_application_funnel.py  # Task 4 validation
├── validate_liquidity_dashboard.py # Task 5 validation (end-to-end)
├── scalability_test.py             # Benchmark at 10x / 50x / 100x
├── dashboard.py                    # Streamlit dashboard — 7 tabs
├── scalability_report.txt          # Auto-generated benchmark report
├── requirements.txt
├── .gitignore
└── README.md
```
