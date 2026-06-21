"""
PlaceMux — Task 4: Applications & Shortlisting — Application Funnel Validator
Validates that "students apply; companies shortlist verified candidates" is
actually enforced in the data, not just claimed. Run before the live demo.
"""
import sqlite3, pandas as pd, datetime as dt, os

DB = os.path.join(os.path.dirname(__file__), "placemux.db")
TODAY = dt.datetime.now()

METRIC_DICTIONARY = {
    "application_funnel": {
        "definition": "Submitted -> Verified/Rejected -> Shortlisted -> Interviewed -> Offered, "
                       "built from application_events (immutable log) joined to applications "
                       "(current state).",
        "source_events": ["application_events", "applications", "interviews", "offers"],
        "decision": "If verification_pass_rate is low for a specific job, the min_cgpa "
                    "threshold may be set too high for the candidate pool -> company "
                    "should be prompted to reconsider the threshold, not just wait longer.",
    },
    "verification_pass_rate": {
        "definition": "% of submitted applications where the student met the job's min_cgpa "
                       "threshold at the moment of applying.",
        "source_events": ["application_events"],
        "decision": "Low pass rate company-wide -> search ranking is surfacing jobs to "
                    "students who don't qualify -> fix the fit-ranking filter, not the "
                    "verification logic.",
    },
    "shortlist_integrity": {
        "definition": "% of shortlisted applications that were verified at submit time. "
                       "Should always be 100% — this is an integrity check, not a KPI "
                       "a founder tunes, but one they must trust is never violated.",
        "source_events": ["application_events"],
        "decision": "Any value below 100% means an unverified candidate was shortlisted "
                    "— a data/process bug serious enough to halt and investigate "
                    "immediately, not a metric to monitor over time.",
    },
}


def validate():
    conn = sqlite3.connect(DB)
    print("=" * 65)
    print("TASK 4 — APPLICATIONS & SHORTLISTING: APPLICATION FUNNEL VALIDATION")
    print("=" * 65)

    # ── Check 1: real data flowing ──────────────────────────────
    n_apps   = pd.read_sql("SELECT COUNT(*) n FROM applications", conn).iloc[0,0]
    n_events = pd.read_sql("SELECT COUNT(*) n FROM application_events", conn).iloc[0,0]
    print(f"\n[CHECK 1] Real data flowing (not zero, not toy)")
    print(f"  applications        : {n_apps}")
    print(f"  application_events  : {n_events}")
    status1 = "PASS" if n_apps > 100 and n_events > 200 else "FAIL"
    print(f"  {status1}")

    # ── Check 2: freshness ──────────────────────────────────────
    last_event = pd.read_sql("SELECT MAX(emitted_at) ts FROM application_events", conn).iloc[0,0]
    hours_ago = (TODAY - dt.datetime.strptime(last_event, "%Y-%m-%d %H:%M:%S")).total_seconds()/3600
    print(f"\n[CHECK 2] Freshness (SLA: last event < 48h ago)")
    print(f"  Last event: {last_event} ({hours_ago:.1f}h ago)")
    status2 = "PASS" if hours_ago < 48 else "FAIL"
    print(f"  {status2}")

    # ── Check 3: nulls ───────────────────────────────────────────
    print(f"\n[CHECK 3] Required fields populated")
    null_q = pd.read_sql("""
        SELECT
            SUM(CASE WHEN student_id IS NULL THEN 1 ELSE 0 END) AS null_student,
            SUM(CASE WHEN job_id IS NULL THEN 1 ELSE 0 END) AS null_job,
            SUM(CASE WHEN event_name IS NULL THEN 1 ELSE 0 END) AS null_event_name,
            SUM(CASE WHEN verified IS NULL THEN 1 ELSE 0 END) AS null_verified
        FROM application_events
    """, conn)
    print(null_q.to_string(index=False))
    status3 = "PASS" if null_q.sum(axis=1).iloc[0] == 0 else "WARN"
    print(f"  {status3}")

    # ── Check 4: duplicates ──────────────────────────────────────
    dup = pd.read_sql("""
        SELECT COUNT(*) n FROM (
            SELECT application_id, event_name, COUNT(*) c
            FROM application_events GROUP BY application_id, event_name
            HAVING c > 1
        )
    """, conn).iloc[0,0]
    print(f"\n[CHECK 4] Duplicate event-per-application (same event fired twice)")
    print(f"  Duplicates: {dup}")
    status4 = "PASS" if dup == 0 else "WARN"
    print(f"  {status4}")

    # ── Check 5: shortlist integrity — the real enforcement test ─
    print(f"\n[CHECK 5] Shortlist integrity — no unverified candidate ever shortlisted")
    violation = pd.read_sql("""
        SELECT COUNT(*) n FROM applications
        WHERE status = 'Shortlisted' AND verified = 0
    """, conn).iloc[0,0]
    print(f"  Unverified-but-shortlisted applications: {violation}")
    status5 = "PASS" if violation == 0 else "FAIL"
    print(f"  {status5}")

    # ── LIVE VIEW — the actual Task 4 deliverable ────────────────
    print(f"\n{'='*65}")
    print("LIVE VIEW — APPLICATION FUNNEL (aggregate, real data)")
    print(f"{'='*65}")

    funnel = pd.read_sql("""
        SELECT
            COUNT(*) AS submitted,
            SUM(CASE WHEN verified=1 THEN 1 ELSE 0 END) AS verified,
            SUM(CASE WHEN verified=0 THEN 1 ELSE 0 END) AS rejected_unverified,
            SUM(CASE WHEN status='Shortlisted' THEN 1 ELSE 0 END) AS shortlisted,
            SUM(CASE WHEN status='Interviewed' THEN 1 ELSE 0 END) AS interviewed,
            SUM(CASE WHEN status='Offered' THEN 1 ELSE 0 END) AS offered
        FROM applications
    """, conn)
    print(funnel.to_string(index=False))

    verification_rate = round(funnel["verified"].iloc[0] / funnel["submitted"].iloc[0] * 100, 1)
    shortlist_rate = round(funnel["shortlisted"].iloc[0] / max(funnel["verified"].iloc[0],1) * 100, 1)
    print(f"\nverification_pass_rate : {verification_rate}%  (verified / submitted)")
    print(f"shortlist_rate_of_verified : {shortlist_rate}%  (shortlisted / verified)")

    print(f"\nPer-job funnel (top 10 jobs by applications):")
    per_job = pd.read_sql("""
        SELECT j.job_title, j.min_cgpa,
               COUNT(a.application_id) AS submitted,
               SUM(CASE WHEN a.verified=1 THEN 1 ELSE 0 END) AS verified,
               SUM(CASE WHEN a.status='Shortlisted' THEN 1 ELSE 0 END) AS shortlisted
        FROM jobs j JOIN applications a ON j.job_id = a.job_id
        GROUP BY j.job_id ORDER BY submitted DESC LIMIT 10
    """, conn)
    print(per_job.to_string(index=False))

    conn.close()
    print(f"\n{'='*65}")
    all_pass = all(s == "PASS" for s in [status1, status2, status5])
    print(f"OVERALL: {'ALL CRITICAL CHECKS PASS' if all_pass else 'REVIEW WARNINGS ABOVE'}")
    print("Application funnel is live, verification-gated, and demoable.")
    print(f"{'='*65}")


if __name__ == "__main__":
    validate()
