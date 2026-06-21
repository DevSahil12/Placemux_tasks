import sqlite3

conn = sqlite3.connect("placemux.db")
cur = conn.cursor()

cur.executescript("""
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
""")

conn.commit()
conn.close()
print("Database created with full schema.")
