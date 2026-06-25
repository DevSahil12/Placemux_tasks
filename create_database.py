import sqlite3

conn = sqlite3.connect("placemux.db")
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS conversion_events;
DROP TABLE IF EXISTS student_payments;
DROP TABLE IF EXISTS payment_reconciliation;
DROP TABLE IF EXISTS payment_events;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS application_events;
DROP TABLE IF EXISTS job_view_events;
DROP TABLE IF EXISTS job_search_events;
DROP TABLE IF EXISTS job_supply_events;
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS interviews;
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS companies;

CREATE TABLE companies (
    company_id   INTEGER PRIMARY KEY,
    company_name TEXT,
    industry     TEXT,
    created_at   TEXT,
    status       TEXT
);

CREATE TABLE jobs (
    job_id        INTEGER PRIMARY KEY,
    company_id    INTEGER,
    job_title     TEXT,
    skills        TEXT,
    min_cgpa      REAL,
    salary        INTEGER,
    created_at    TEXT,
    status        TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE students (
    student_id   INTEGER PRIMARY KEY,
    student_name TEXT,
    college      TEXT,
    cgpa         REAL,
    skills       TEXT,
    created_at   TEXT
);

CREATE TABLE applications (
    application_id INTEGER PRIMARY KEY,
    student_id     INTEGER,
    job_id         INTEGER,
    applied_at     TEXT,
    status         TEXT,
    verified       INTEGER DEFAULT 0,   -- 1 = passed skill-threshold check at apply time
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (job_id)     REFERENCES jobs(job_id)
);

CREATE TABLE interviews (
    interview_id   INTEGER PRIMARY KEY,
    application_id INTEGER,
    scheduled_at   TEXT,
    status         TEXT,
    FOREIGN KEY (application_id) REFERENCES applications(application_id)
);

CREATE TABLE offers (
    offer_id       INTEGER PRIMARY KEY,
    application_id INTEGER,
    offered_at     TEXT,
    status         TEXT,
    FOREIGN KEY (application_id) REFERENCES applications(application_id)
);

-- ── TASK 2: Job-supply instrumentation event log ──────────────────────────
-- Every time a job is posted this event fires and lands here.
-- Columns mirror the tracking plan payload exactly.
CREATE TABLE job_supply_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name    TEXT    DEFAULT 'job_posted',
    job_id        INTEGER,
    company_id    INTEGER,
    job_title     TEXT,
    skills        TEXT,
    min_cgpa      REAL,
    salary        INTEGER,
    status        TEXT,
    emitted_at    TEXT,
    FOREIGN KEY (job_id)    REFERENCES jobs(job_id),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ── TASK 3: Search & Discovery ─────────────────────────────────────────────
-- Every search a student runs lands here. Powers search_to_view_rate,
-- search_latency_p95, zero_result_rate, and the fit-ranking shown to students.
CREATE TABLE job_search_events (
    search_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER,
    query         TEXT,
    result_count  INTEGER,
    latency_ms    INTEGER,
    clicked_job_id INTEGER,
    fit_score     REAL,
    searched_at   TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (clicked_job_id) REFERENCES jobs(job_id)
);

-- Every time a student views a job (from search or browse), this fires.
-- This is the event the company funnel's "Viewed" stage is built on.
CREATE TABLE job_view_events (
    view_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER,
    job_id        INTEGER,
    source        TEXT,      -- 'search' or 'browse'
    fit_score     REAL,
    viewed_at     TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (job_id)     REFERENCES jobs(job_id)
);

-- ── TASK 4: Applications & Shortlisting ────────────────────────────────────
-- Immutable event log — every status change in an application's life fires
-- a row here. The applications table holds *current* state; this table
-- holds the *history* the funnel and freshness checks are built on.
CREATE TABLE application_events (
    app_event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER,
    student_id      INTEGER,
    job_id          INTEGER,
    company_id      INTEGER,
    event_name      TEXT,     -- application_submitted | application_verified |
                              -- application_rejected_unverified | application_shortlisted
    verified        INTEGER,  -- 1/0 — did the student meet the job's min_cgpa at this event
    emitted_at      TEXT,
    FOREIGN KEY (application_id) REFERENCES applications(application_id),
    FOREIGN KEY (student_id)     REFERENCES students(student_id),
    FOREIGN KEY (job_id)         REFERENCES jobs(job_id),
    FOREIGN KEY (company_id)     REFERENCES companies(company_id)
);

-- ── TASK 6: Payments Design & Gateway Setup ────────────────────────────────
-- payments: entity table — one row per transaction, mutable (status can change).
-- Revenue model: companies pay per shortlist or per job slot (test-mode gateway).
CREATE TABLE payments (
    payment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER,
    job_id          INTEGER,
    application_id  INTEGER,
    payment_type    TEXT,    -- 'per_shortlist' | 'job_slot' | 'subscription'
    amount_inr      REAL,
    currency        TEXT DEFAULT 'INR',
    gateway_ref     TEXT,    -- reference ID returned by payment gateway
    gateway_mode    TEXT DEFAULT 'test',  -- 'test' | 'live'
    status          TEXT,    -- 'initiated' | 'success' | 'failed' | 'refunded'
    failure_reason  TEXT,
    initiated_at    TEXT,
    resolved_at     TEXT,
    FOREIGN KEY (company_id)     REFERENCES companies(company_id),
    FOREIGN KEY (job_id)         REFERENCES jobs(job_id),
    FOREIGN KEY (application_id) REFERENCES applications(application_id)
);

-- payment_events: immutable audit log — every status change fires a row here.
-- Answers: "how do we know records match exactly what the gateway collected?"
CREATE TABLE payment_events (
    pe_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id      INTEGER,
    company_id      INTEGER,
    event_name      TEXT,    -- payment_initiated | payment_success | payment_failed |
                             -- payment_refunded | gateway_reconciled
    amount_inr      REAL,
    gateway_ref     TEXT,
    gateway_mode    TEXT,
    failure_reason  TEXT,
    emitted_at      TEXT,
    FOREIGN KEY (payment_id) REFERENCES payments(payment_id),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- payment_reconciliation: daily summary comparing our DB records vs gateway records.
-- Answers: "how do we know our records match exactly what the gateway says we collected?"
CREATE TABLE payment_reconciliation (
    recon_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recon_date      TEXT,
    our_count       INTEGER,  -- payments we recorded as success
    our_total_inr   REAL,     -- total INR we recorded
    gateway_count   INTEGER,  -- what the gateway API reports for that date
    gateway_total_inr REAL,
    matched         INTEGER,  -- 1 if counts and totals agree, 0 if discrepancy
    discrepancy_inr REAL,     -- our_total - gateway_total (0 if matched)
    notes           TEXT,
    created_at      TEXT
);
""")

conn.commit()
conn.close()
print("Database created with full schema.")
# Task 7 tables added separately to avoid executescript conflicts
import sqlite3 as _sqlite3
_conn = _sqlite3.connect("placemux.db")
_conn.executescript("""
DROP TABLE IF EXISTS conversion_events;
DROP TABLE IF EXISTS student_payments;

CREATE TABLE IF NOT EXISTS student_payments (
    sp_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER,
    job_id          INTEGER,
    application_id  INTEGER,
    amount_inr      REAL DEFAULT 100,
    gateway_ref     TEXT,
    gateway_mode    TEXT DEFAULT 'test',
    status          TEXT,
    failure_reason  TEXT,
    initiated_at    TEXT,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS conversion_events (
    ce_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER,
    job_id          INTEGER,
    sp_id           INTEGER,
    application_id  INTEGER,
    event_name      TEXT,
    amount_inr      REAL,
    failure_reason  TEXT,
    gateway_mode    TEXT DEFAULT 'test',
    emitted_at      TEXT
);
""")
_conn.commit()
_conn.close()
