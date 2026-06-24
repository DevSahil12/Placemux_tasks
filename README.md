# 📊 PlaceMux — Marketplace Analytics

> **Phase 2 · Week 3 · Data Analyst Track — Tasks 1–6 Complete**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://placemux-analytics.streamlit.app)

---

## 🚀 Live Dashboard

**[▶ Open Live Dashboard](https://placemux-analytics.streamlit.app)**

*Deployed on Streamlit Cloud — no setup needed, opens in browser.*

To run locally instead:
```bash
git clone https://github.com/<your-username>/placemux-analytics.git
cd placemux-analytics
pip install -r requirements.txt
python3 create_database.py
python3 live_data.py seed
streamlit run dashboard.py        # → http://localhost:8501
```

---

## 📸 Dashboard — Live Numbers

> These are real numbers computed from the seeded database — not placeholders.

### 💧 Liquidity Index: **82.6 / 100 [HEALTHY]**
> Marketplace healthy — continue onboarding companies.

| Component | Weight | Score |
|---|---|---|
| Fill Proxy (apply→shortlist rate) | 35% | 45.1% |
| Supply Health (active listings) | 30% | 100.0 |
| Discovery (search→view rate) | 20% | 53.4% |
| Verification Quality | 15% | 67.8% |

### 📊 End-to-End Funnel (company posts → student applies → company shortlists)

| Stage | Count |
|---|---|
| Posted | 300 |
| Viewed | 1,083 |
| Applied | 1,506 |
| Verified | 1,021 |
| Shortlisted+ | 460 |
| Offered | 134 |

### 💰 Revenue Metrics (Task 6) — Gateway Mode: **TEST**

| Payment Type | Transactions | Successful | Revenue (INR) |
|---|---|---|---|
| job_slot | 236 | 199 | ₹5,96,801 |
| per_shortlist | 460 | 379 | ₹1,89,500 |
| subscription | 12 | 11 | ₹1,09,989 |
| **Total** | **708** | **589** | **₹8,96,290** |

| Metric | Value |
|---|---|
| Payment Success Rate | 83.2% |
| Paying Companies | 78 / 80 |
| ARPC (Avg Revenue per Company) | ₹11,491 |
| Gateway Mode | **test** (no real money) |
| Shortlist Integrity | **100%** (0 violations) |

---

## Architecture

```
Backend API
    ├─ job_posted ──────────────▶ emit_job_posted()
    │                                └──▶ job_supply_events     (Task 2)
    ├─ student searches ────────▶ emit_job_search()
    │                                └──▶ job_search_events     (Task 3)
    │                                └──▶ job_view_events       (Task 3)
    ├─ student applies ─────────▶ emit_application() [verifies min_cgpa]
    │                                └──▶ application_events    (Task 4)
    ├─ company shortlists ──────▶ emit_shortlist() [refuses if unverified]
    └─ company pays ────────────▶ emit_payment()
                                     ├──▶ payments              (Task 6)
                                     └──▶ payment_events        (Task 6)
                                              │
                              liquidity_engine.py + revenue_engine.py
                                              │
                              dashboard.py — 8 tabs
```

---

## Database Schema

> Full explanation of every table: see **[SCHEMA.md](./SCHEMA.md)**

| Table | Type | Task | Purpose |
|---|---|---|---|
| `companies` | Entity | 1 | Company master records |
| `jobs` | Entity | 1 | Job postings with skill thresholds |
| `students` | Entity | 1 | Candidate profiles with CGPA |
| `applications` | Entity | 1/4 | Applications with `verified` flag |
| `interviews` | Entity | 1 | Interview scheduling |
| `offers` | Entity | 1 | Final-stage offers |
| `job_supply_events` | **Event log** | 2 | Every job posting, immutable |
| `job_search_events` | **Event log** | 3 | Every search with latency + fit score |
| `job_view_events` | **Event log** | 3 | Every job view (search or browse) |
| `application_events` | **Event log** | 4 | Full application status history |
| `payments` | Entity | 6 | Payment transactions with gateway status |
| `payment_events` | **Event log** | 6 | Immutable payment audit trail |
| `payment_reconciliation` | Audit | 6 | Daily DB vs gateway comparison |
| `sqlite_sequence` | **SQLite internal** | — | Auto-created, safe to ignore |

---

## Task Deliverables

| Task | Deliverable | Validator | Status |
|---|---|---|---|
| Task 1 | Marketplace schema, liquidity metrics, tracking plan | — | ✅ |
| Task 2 | `job_supply_events`, live jobs-posted view | `validate_job_supply.py` | ✅ |
| Task 3 | Search events, fit-score ranking, company funnel | `validate_company_funnel.py` | ✅ |
| Task 4 | Verification gate, application funnel, integrity check | `validate_application_funnel.py` | ✅ |
| Task 5 | Liquidity Index (82.6/100), 14 metrics, end-to-end dashboard | `validate_liquidity_dashboard.py` | ✅ |
| Task 6 | Revenue metrics, payment events, gateway reconciliation | `validate_revenue_metrics.py` | ✅ |

### Task 6 Self-Check Answers
- *What happens if a payment fails halfway?* `emit_payment()` fires `payment_failed` event, sets `status='failed'`. The student's application is **not touched** — `emit_shortlist()` is independent of payment outcome. Zero failed-payment applications leaked into shortlisted status (validated by Check 4).
- *How do we know records match what the gateway collected?* `payment_reconciliation` table runs daily — compares our `SUM(amount_inr)` vs gateway API total. Any discrepancy > ₹0.01 flags as unmatched. 7-day history seeded; available in Tab 1 of the dashboard.
- *Are we in test mode or live mode?* **Test mode confirmed** — 0 payments processed with `gateway_mode='live'`. Remaining steps before real money: go-live checklist sign-off, production gateway credentials, failure alerting wired to on-call.

---

## Revenue Metric Definitions (Task 6 Tracking Plan Addition)

| Event | Fires When | Key Payload |
|---|---|---|
| `payment_initiated` | Company attempts payment | `amount_inr`, `payment_type`, `gateway_ref`, `gateway_mode` |
| `payment_success` | Gateway confirms collection | `amount_inr`, `gateway_ref` |
| `payment_failed` | Gateway rejects payment | `failure_reason`, `gateway_ref` |
| `payment_refunded` | Refund issued | `amount_inr`, `gateway_ref` |

---

## Files

```
placemux-analytics/
├── create_database.py              # 13-table schema (11 domain + 2 infra)
├── live_data.py                    # Live pipeline: job_posted / search / apply / pay
├── revenue_engine.py               # Task 6: revenue metric computation
├── liquidity_engine.py             # Task 5: liquidity index computation
├── validate_job_supply.py          # Task 2 validation
├── validate_company_funnel.py      # Task 3 validation
├── validate_application_funnel.py  # Task 4 validation
├── validate_liquidity_dashboard.py # Task 5 validation
├── validate_revenue_metrics.py     # Task 6 validation
├── scalability_test.py             # 10x / 50x / 100x benchmarks
├── dashboard.py                    # Streamlit — 8 tabs
├── SCHEMA.md                       # Every table explained + defended
├── requirements.txt
├── .gitignore
└── README.md
```
