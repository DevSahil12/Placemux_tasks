# 📊 PlaceMux — Marketplace Analytics

> **Phase 2 · Week 3 · Data Analyst Track — Tasks 1–7 Complete**

---

## 🚀 Deploy to Streamlit Cloud (5 minutes)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Select your repo → branch: `master` → main file: `dashboard.py`
4. Click **Deploy** — Streamlit Cloud installs `requirements.txt` automatically
5. Paste the live URL in your submission

> **Note:** The `.db` file is excluded from git (`.gitignore`). Streamlit Cloud will run `create_database.py` + `live_data.py seed` automatically if you add a `streamlit_app.py` wrapper (see `streamlit_app.py` in this repo).

---

## ▶ Run Locally

```bash
git clone https://github.com/<your-username>/placemux-analytics.git
cd placemux-analytics
pip install -r requirements.txt

python3 create_database.py              # build schema (15 tables)
python3 live_data.py seed               # seed all data including ₹100 conversion flow
streamlit run dashboard.py              # → http://localhost:8501
```

---

## 📸 Live Numbers — Real Data, No Placeholders

> These are computed directly from the seeded database.
> Every number below is explained with its formula.

### 💧 Liquidity Index: **76.2 / 100 [HEALTHY]**
> Marketplace healthy — continue onboarding companies.

### 🔁 Conversion Baseline (Task 7) — Student Pay ₹100 to Apply

| Metric | Value | How it's calculated |
|---|---|---|
| End-to-End Conversion Rate | **79.8%** | `COUNT(application_created) / COUNT(job_viewed) × 100` |
| Payment Success Rate | **79.8%** | `COUNT(pay_per_app_success) / COUNT(pay_per_app_initiated) × 100` |
| Pay→App Integrity | **100%** | `COUNT(application_created) / COUNT(pay_per_app_success) × 100` |
| Abandonment Rate | **10.0%** | `COUNT(application_abandoned) / COUNT(pay_per_app_initiated) × 100` |
| Revenue (₹100 fees) | **₹47,900** | `SUM(amount_inr) FROM student_payments WHERE status='success'` |
| Avg Convert Time | **5s** | `AVG(resolved_at - initiated_at) FROM student_payments WHERE status='success'` |
| Gateway Mode | **test** | `DISTINCT(gateway_mode) FROM student_payments` |

### 💰 Revenue (Task 6) — Company Payments

| Payment Type | Transactions | Revenue |
|---|---|---|
| job_slot | 193 | ₹5,78,807 |
| per_shortlist | 396 | ₹1,98,000 |
| subscription | 11 | ₹1,09,989 |
| **Total** | **77 companies** | **₹8,86,796** |

### 📊 End-to-End Funnel

| Stage | Count |
|---|---|
| Posted | 300 |
| Viewed | 1,162 |
| Applied (paid ₹100) | 479 |
| Applied (direct) | 1,370 |
| Shortlisted+ | 472 |
| Offered | 156 |

---

## ⚠️ Error Handling — How It Actually Works

### What happens when a student's ₹100 payment fails?

**The student loses nothing.** Here is the exact sequence:

```
1. pay_per_app_initiated fires  → student clicked "Apply & Pay ₹100"
2. Gateway returns failure      → e.g. failure_reason = "card_declined"
3. pay_per_app_failed fires     → event logged with failure_reason
4. student_payments.status = 'failed'
5. application_created NEVER fires → NO application row created
6. student_payments.application_id = NULL (confirmed by Check 5 in validator)
```

**Verified by data:** 0 failed payments have an `application_id` — confirmed by `validate_conversion_baseline.py` Check 5.

### What happens if the student abandons mid-payment?

Same outcome — `application_abandoned` fires after 30-min timeout, no application created, no charge taken.

### Payment failure breakdown (real data)

| Failure Reason | % of Failures |
|---|---|
| net_banking_error | 26.2% |
| upi_timeout | 23.0% |
| insufficient_funds | 18.0% |
| gateway_timeout | 16.4% |
| card_declined | 16.4% |

**Decision:** `upi_timeout` at 23% → UPI timeout SLA needs extending. `net_banking_error` at 26% → add more net banking options or promote UPI/wallet as primary.

---

## Architecture

```
Student Flow (Task 7)
    student views job ──▶ job_viewed event
    student clicks Apply & Pay ──▶ pay_per_app_initiated event
                                      │
                              gateway response
                             /                \
                    SUCCESS (79.8%)       FAILURE (10.2%)  ABANDON (10%)
                       │                      │                 │
              pay_per_app_success      pay_per_app_failed  application_abandoned
                       │                      │                 │
              application_created       NO APP CREATED    NO APP CREATED
              student_payments.         student_payments. student_payments.
              application_id = X        application_id = NULL (enforced)
```

---

## Metric Calculation Reference

Every metric in the dashboard has an expandable "How it's calculated" section showing:
- Exact SQL formula
- Source table and column
- Expected range
- Decision it informs

This is visible in the **🔁 Conversion (Task 7)** tab, **💰 Revenue (Task 6)** tab, and **💧 Liquidity (Task 5)** tab.

---

## All Validators Pass

```bash
python3 validate_job_supply.py          # Task 2: 5/5 PASS
python3 validate_company_funnel.py      # Task 3: 5/5 PASS
python3 validate_application_funnel.py  # Task 4: 5/5 PASS
python3 validate_liquidity_dashboard.py # Task 5: 5/5 PASS
python3 validate_revenue_metrics.py     # Task 6: 5/5 PASS
python3 validate_conversion_baseline.py # Task 7: 5/5 PASS
```

---

## Database Schema

> Full explanation: **[SCHEMA.md](./SCHEMA.md)**

| Table | Type | Task | Purpose |
|---|---|---|---|
| `companies`, `jobs`, `students` | Entity | 1 | Core marketplace entities |
| `applications`, `interviews`, `offers` | Entity | 1 | Hiring pipeline |
| `job_supply_events` | Event log | 2 | Every job posting |
| `job_search_events`, `job_view_events` | Event log | 3 | Discovery tracking |
| `application_events` | Event log | 4 | Application audit trail |
| `payments`, `payment_events` | Entity + log | 6 | Company payment tracking |
| `payment_reconciliation` | Audit | 6 | Daily DB vs gateway comparison |
| `student_payments` | Entity | 7 | ₹100 student payment flow |
| `conversion_events` | Event log | 7 | Full conversion funnel log |
| `sqlite_sequence` | SQLite internal | — | Auto-created, safe to ignore |

---

## Files

```
placemux-analytics/
├── create_database.py              # 15-table schema
├── live_data.py                    # Live pipeline + seed + pay-per-app
├── conversion_engine.py            # Task 7: conversion metrics + error examples
├── revenue_engine.py               # Task 6: revenue metrics
├── liquidity_engine.py             # Task 5: liquidity index
├── validate_conversion_baseline.py # Task 7 validation (5 checks)
├── validate_revenue_metrics.py     # Task 6 validation
├── validate_liquidity_dashboard.py # Task 5 validation
├── validate_application_funnel.py  # Task 4 validation
├── validate_company_funnel.py      # Task 3 validation
├── validate_job_supply.py          # Task 2 validation
├── scalability_test.py             # 10x / 50x / 100x benchmarks
├── dashboard.py                    # Streamlit — 9 tabs
├── SCHEMA.md                       # Every table explained + defended
├── requirements.txt                # Pinned versions for Streamlit Cloud
├── .gitignore
└── README.md
```

---

## Task 8 — Receipts, Refunds & Reconciliation

### 🔄 Refund/Failure Analytics (Live Numbers)

| Metric | Value | Formula |
|---|---|---|
| total_receipts_issued | 1,063 | `COUNT(*) FROM receipts` |
| receipt_coverage_rate | **100%** | `COUNT(receipts)/COUNT(success_payments)×100` |
| total_refunds_issued | 103 | `COUNT(*) FROM refunds` |
| refund_rate | **9.7%** | `COUNT(refunds)/COUNT(receipts)×100` |
| refund_success_rate | 93.2% | `COUNT(status='processed')/COUNT(refunds)×100` |
| total_refunded_inr | ₹96,081 | `SUM(amount_inr) WHERE status='processed'` |
| net_revenue_inr | **₹8,25,617** | `gross_revenue - total_refunded` |
| failed_refunds_needing_retry | 7 | `COUNT(*) WHERE status='failed'` — action within 24h |
| reconciliation_match_rate | **100%** | `SUM(matched)/COUNT(*)×100` |

### Refunds by Reason

| Reason | Count | Amount (INR) |
|---|---|---|
| duplicate_transaction | 28 | ₹43,194 |
| gateway_error | 23 | ₹13,397 |
| manual_review | 17 | ₹25,993 |
| candidate_withdrew | 14 | ₹1,400 |
| payment_failed | 12 | ₹1,200 |
| company_cancelled | 9 | ₹11,997 |

**Decision:** `duplicate_transaction` at 28 = add idempotency key to payment flow urgently. `gateway_error` at 23 = escalate to gateway provider.

### How Receipts & Refunds Work (Error Handling)

```
Successful payment
      │
      ▼
emit_receipt() → receipts table (receipt_number = RCP-2026-XXXXXX)
      │
   (if refund needed)
      ▼
emit_refund(receipt_id, reason)
      │
      ├─ refund_initiated event → refund_events log
      │
      ▼ gateway response
     93.2%              6.8%
  refund_processed   refund_failed
      │                   │
  refund_events       refund_events
  status='processed'  status='failed'
                          │
                    → listed in dashboard
                      "Failed Refunds Needing Retry"
                      → action within 24h
```

**Key rules enforced in code:**
1. No refund without a receipt (`receipt_id` FK enforced)
2. Refund amount cannot exceed original payment amount
3. Failed refunds are tracked and surfaced — never silently dropped
4. Gateway reconciliation runs daily — any discrepancy > ₹0.01 flagged

### New Tables (Task 8)

| Table | Type | Purpose |
|---|---|---|
| `receipts` | Entity | One per successful payment — customer proof, refund prerequisite |
| `refunds` | Entity | Refund transactions — current state |
| `refund_events` | Event log | Immutable audit trail of every refund status change |
