# PlaceMux — Database Schema Reference

This document explains every table: what it is, why it exists, and which
tables feed which metrics. Written to address the evaluator feedback from
Task 5: "some tables seem unnecessary."

**None of the tables are unnecessary.** They fall into two clear categories:

---

## Table Categories

| Category | Pattern | Tables |
|---|---|---|
| **Entity tables** | Mutable — current state only | `companies`, `jobs`, `students`, `applications`, `interviews`, `offers`, `payments` |
| **Event log tables** | Immutable — full audit trail | `job_supply_events`, `job_search_events`, `job_view_events`, `application_events`, `payment_events` |

### Why two patterns?

**Entity tables** answer "what is the current state?" — e.g. `applications.status = 'Offered'`.

**Event log tables** answer "what happened and when?" — e.g. `application_events` shows the full journey: `application_submitted → application_verified → application_shortlisted`.

The entity table alone can't reconstruct history. The event log alone doesn't give you a fast "how many open jobs right now?" query. **Both are needed**, and this is standard practice in any data platform (see: event sourcing, CDC).

`sqlite_sequence` is an **internal SQLite system table** — auto-created whenever any table uses `AUTOINCREMENT`. It is not a user table and plays no role in the application.

---

## Entity Tables

### `companies`
Stores each company that signs up to post jobs.

| Column | Type | Description |
|---|---|---|
| company_id | INTEGER PK | Unique identifier |
| company_name | TEXT | Display name |
| industry | TEXT | SaaS / Fintech / EdTech etc. |
| created_at | TEXT | Signup timestamp |
| status | TEXT | active / inactive |

**Feeds:** `supply_growth_wow`, `conversion_to_paid_rate`, `company_funnel`

---

### `jobs`
One row per job posted. Status changes as jobs are filled or expired.

| Column | Type | Description |
|---|---|---|
| job_id | INTEGER PK | Unique identifier |
| company_id | INTEGER FK | Which company posted it |
| job_title | TEXT | Role name |
| skills | TEXT | Comma-separated skill requirements |
| min_cgpa | REAL | **Skill threshold** — applications below this are `verified=0` |
| salary | INTEGER | Offered CTC in INR |
| created_at | TEXT | When posted |
| status | TEXT | open / closed / filled |

**Feeds:** `active_listings`, `avg_min_cgpa_threshold`, `verification_pass_rate`

---

### `students`
One row per registered student/candidate.

| Column | Type | Description |
|---|---|---|
| student_id | INTEGER PK | Unique identifier |
| student_name | TEXT | Display name |
| college | TEXT | Institution |
| cgpa | REAL | Grade point average — compared against `jobs.min_cgpa` at apply time |
| skills | TEXT | Student's self-reported skills |
| created_at | TEXT | Registration timestamp |

**Feeds:** `verification_pass_rate`, `fit_score` computation, `search_to_view_rate`

---

### `applications`
Current state of each student–job application. Mutable — `status` and `verified` change over time.

| Column | Type | Description |
|---|---|---|
| application_id | INTEGER PK | Unique identifier |
| student_id | INTEGER FK | Which student |
| job_id | INTEGER FK | Which job |
| applied_at | TEXT | Submission timestamp |
| status | TEXT | Applied / Shortlisted / Interviewed / Offered / Rejected |
| verified | INTEGER | **1** if student.cgpa ≥ job.min_cgpa at apply time, else **0** |

`verified` is set once at submission time and never changed. This is the enforcement point for "companies shortlist verified candidates" — `emit_shortlist()` refuses if `verified=0`.

**Feeds:** `verification_pass_rate`, `apply_to_shortlist_rate`, `shortlist_integrity`

---

### `interviews`
Scheduled interview records for shortlisted applications.

| Column | Type | Description |
|---|---|---|
| interview_id | INTEGER PK | Unique identifier |
| application_id | INTEGER FK | Which application |
| scheduled_at | TEXT | Interview datetime |
| status | TEXT | Scheduled / Completed / Cancelled |

**Feeds:** `shortlist_to_interview_rate`

---

### `offers`
Offer records for applications that reached the Offered stage.

| Column | Type | Description |
|---|---|---|
| offer_id | INTEGER PK | Unique identifier |
| application_id | INTEGER FK | Which application |
| offered_at | TEXT | Offer datetime |
| status | TEXT | Pending / Accepted / Declined |

**Feeds:** `interview_to_offer_rate`

---

### `payments` *(Task 6)*
One row per payment transaction. Mutable — `status` changes as gateway responds.

| Column | Type | Description |
|---|---|---|
| payment_id | INTEGER PK | Unique identifier |
| company_id | INTEGER FK | Paying company |
| job_id | INTEGER FK | Related job (nullable for subscriptions) |
| application_id | INTEGER FK | Related shortlist (per_shortlist type only) |
| payment_type | TEXT | per_shortlist / job_slot / subscription |
| amount_inr | REAL | Charge amount in INR |
| currency | TEXT | INR (fixed for now) |
| gateway_ref | TEXT | Gateway's own reference ID (reconciliation key) |
| gateway_mode | TEXT | **test** (never live until founder sign-off) |
| status | TEXT | initiated / success / failed / refunded |
| failure_reason | TEXT | Populated if status=failed |
| initiated_at | TEXT | When PlaceMux sent the charge |
| resolved_at | TEXT | When gateway responded |

**Feeds:** `total_revenue_inr`, `payment_success_rate`, `arpc_inr`, `refund_rate`

---

## Event Log Tables

### `job_supply_events` *(Task 2)*
Fires once per job posted. The instrumentation layer for supply-side metrics.

**Why separate from `jobs`?** The `jobs` table is mutable — when a job is filled, `status` changes. The event log preserves the immutable record of when and how each job was posted, enabling time-series queries without scanning mutable state.

**Feeds:** `jobs_posted_last_7d`, `supply_growth_wow`, `search_latency_p95`

---

### `job_search_events` *(Task 3)*
Fires once per search performed by a student. Records query, result count, latency, and the fit score of the top result.

**Why separate from `students`?** A student performs many searches. The event log captures each one independently, enabling funnel analysis (search → click → view → apply) that an entity table can't provide.

**Feeds:** `search_to_view_rate`, `search_latency_p95`, `zero_result_rate`, `avg_fit_score`

---

### `job_view_events` *(Task 3)*
Fires once per job view (from search click or direct browse). Records fit score at view time.

**Feeds:** `search_to_view_rate`, `company_funnel` (Viewed stage)

---

### `application_events` *(Task 4)*
Immutable audit log of every application status change. Each application generates at minimum two rows: `application_submitted` and `application_verified` or `application_rejected_unverified`. Shortlisted applications generate a third: `application_shortlisted`.

**Why separate from `applications`?** `applications.status` only holds the current state. `application_events` holds the full timestamped history, which is required for: funnel drop-off analysis, freshness checks, and auditing that no unverified candidate was ever shortlisted.

**Feeds:** `verification_pass_rate`, `shortlist_integrity`, freshness checks

---

### `payment_events` *(Task 6)*
Immutable audit log of every payment status transition. Each payment generates at minimum two rows: `payment_initiated` and `payment_success` / `payment_failed`.

**Why separate from `payments`?** Same reason as `application_events`: the entity table holds current state, the event log holds the audit trail. `gateway_ref` in this table is the **reconciliation key** — it matches our event rows to the gateway's own settlement file, answering "how do we know our records match exactly what the gateway collected?"

**Feeds:** `total_revenue_inr`, `revenue_last_7d`, `failure_reason_breakdown`, reconciliation

---

## Metric → Table Reference

| Metric | Primary Table(s) |
|---|---|
| active_listings | jobs |
| supply_growth_wow | job_supply_events |
| search_to_view_rate | job_search_events + job_view_events |
| search_latency_p95 | job_search_events |
| verification_pass_rate | applications |
| shortlist_integrity | applications |
| apply_to_shortlist_rate | applications |
| liquidity_index | all of the above |
| total_revenue_inr | payment_events |
| payment_success_rate | payments |
| arpc_inr | payments |
| failure_reason_breakdown | payment_events |
| gateway_reconciliation | payment_events (via gateway_ref) |

---

### `receipts` — Entity Table (Task 8)
**Purpose:** One receipt per successful payment (company or student). The receipt is the customer's proof of payment and the mandatory prerequisite for issuing a refund — no receipt, no refund.
**Key columns:** `receipt_number` (human-readable e.g. RCP-2026-000001), `payment_source` (company/student), `refund_eligible`
**Why separate from `payments`?** A receipt is a customer-facing document. Payments are an internal ledger entry. Keeping them separate means receipt formatting, numbering, and delivery can evolve independently of payment logic.

---

### `refunds` — Entity Table (Task 8)
**Purpose:** Current state of every refund transaction.
**Key columns:** `reason`, `initiated_by` (system/founder/gateway), `status` (initiated/processed/failed), `amount_inr` (supports partial refunds)
**Why it exists:** Refunds must be tracked separately from payments because they are debits in the ledger (payments are credits). They also have their own lifecycle: a refund can fail at the gateway even after being initiated.

---

### `refund_events` — Event Log (Task 8)
**Purpose:** Immutable audit trail — every refund status change fires a row here.
**Event types:** `refund_initiated`, `refund_processed`, `refund_failed`
**Why separate from `refunds`?** Same pattern as `payment_events` vs `payments`. If a customer disputes a refund, the event log is the legal record of exactly when each status change happened. The `refunds` table only shows current state.

---

## Summary: Task 8 added 3 tables

| Table | Type | Task 8 Role |
|---|---|---|
| `receipts` | Entity | Proof of payment; refund prerequisite |
| `refunds` | Entity | Refund current state |
| `refund_events` | Event log | Refund audit trail |
