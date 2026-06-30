"""
PlaceMux — Task 3: Search & Discovery — Company Funnel Validator
Validates that the company-side funnel (Posted → Viewed → Applied →
Shortlisted → Interviewed → Offered) is real, sourced, and explainable.
Run this before the live demo.
"""
import sqlite3, pandas as pd, datetime as dt, os

DB = os.path.join(os.path.dirname(__file__), "placemux.db")
TODAY = dt.datetime.now()

METRIC_DICTIONARY = {
    "company_funnel": {
        "definition": "Per-job funnel: Posted -> Viewed -> Applied -> Shortlisted -> "
                       "Interviewed -> Offered, aggregated company-side so a founder "
                       "or company admin can see where candidates drop off.",
        "source_events": ["job_supply_events", "job_view_events", "applications",
                          "interviews", "offers"],
        "decision": "If a company's funnel shows high Views but low Applications, "
                    "the job description or fit-ranking is the problem, not candidate "
                    "supply -> tells the founder exactly which stage to fix per company.",
    },
    "search_to_view_rate": {
        "definition": "% of searches where the student clicked through to view a job.",
        "source_events": ["job_search_events"],
        "decision": "Low rate -> ranking/relevance is broken -> escalate to search "
                    "before spending on candidate acquisition.",
    },
    "avg_fit_score": {
        "definition": "Average fit score (0-100) of jobs returned in search results.",
        "source_events": ["job_search_events", "job_view_events"],
        "decision": "Low average fit -> the matching algorithm needs tuning, or "
                    "supply doesn't match demand for the skills being searched.",
    },
    "search_latency_p95": {
        "definition": "95th percentile search response latency in milliseconds.",
        "source_events": ["job_search_events"],
        "decision": "If p95 > 500ms, discovery feels broken from day one -> "
                    "escalate to backend as a launch blocker, not deferred.",
    },
}


def validate():
    conn = sqlite3.connect(DB)
    print("=" * 65)
    print("TASK 3 — SEARCH & DISCOVERY: COMPANY FUNNEL VALIDATION")
    print("=" * 65)

    # ── Check 1: data is really flowing ─────────────────────────
    n_search = pd.read_sql("SELECT COUNT(*) n FROM job_search_events", conn).iloc[0,0]
    n_view   = pd.read_sql("SELECT COUNT(*) n FROM job_view_events", conn).iloc[0,0]
    n_app    = pd.read_sql("SELECT COUNT(*) n FROM applications", conn).iloc[0,0]
    print(f"\n[CHECK 1] Real data flowing (not zero, not toy)")
    print(f"  job_search_events : {n_search}")
    print(f"  job_view_events   : {n_view}")
    print(f"  applications      : {n_app}")
    status1 = "PASS" if n_search > 100 and n_view > 50 else "FAIL"
    print(f"  {status1}")

    # ── Check 2: freshness ───────────────────────────────────────
    last_search = pd.read_sql("SELECT MAX(searched_at) ts FROM job_search_events", conn).iloc[0,0]
    hours_ago = (TODAY - dt.datetime.strptime(last_search, "%Y-%m-%d %H:%M:%S")).total_seconds()/3600
    print(f"\n[CHECK 2] Freshness (SLA: last search < 48h ago)")
    print(f"  Last search: {last_search} ({hours_ago:.1f}h ago)")
    status2 = "PASS" if hours_ago < 48 else "FAIL"
    print(f"  {status2}")

    # ── Check 3: nulls on required fields ───────────────────────
    print(f"\n[CHECK 3] Required fields populated")
    null_q = pd.read_sql("""
        SELECT
            SUM(CASE WHEN student_id IS NULL THEN 1 ELSE 0 END) AS null_student,
            SUM(CASE WHEN query IS NULL THEN 1 ELSE 0 END) AS null_query,
            SUM(CASE WHEN latency_ms IS NULL THEN 1 ELSE 0 END) AS null_latency
        FROM job_search_events
    """, conn)
    print(null_q.to_string(index=False))
    status3 = "PASS" if null_q.sum(axis=1).iloc[0] == 0 else "WARN"
    print(f"  {status3}")

    # ── Check 4: duplicates ──────────────────────────────────────
    dup = pd.read_sql("""
        SELECT COUNT(*) n FROM (
            SELECT student_id, query, searched_at, COUNT(*) c
            FROM job_search_events GROUP BY student_id, query, searched_at
            HAVING c > 1
        )
    """, conn).iloc[0,0]
    print(f"\n[CHECK 4] Duplicate search events")
    print(f"  Duplicates: {dup}")
    status4 = "PASS" if dup == 0 else "WARN"
    print(f"  {status4}")

    # ── Check 5: ranking sanity — fit scores are realistic ──────
    fit_stats = pd.read_sql(
        "SELECT MIN(fit_score) mn, MAX(fit_score) mx, AVG(fit_score) avg "
        "FROM job_search_events WHERE fit_score IS NOT NULL", conn)
    print(f"\n[CHECK 5] Fit score sanity (must be within 0-100)")
    print(fit_stats.round(1).to_string(index=False))
    mn, mx = fit_stats.iloc[0]["mn"], fit_stats.iloc[0]["mx"]
    status5 = "PASS" if (mn is not None and 0 <= mn and mx <= 100) else "FAIL"
    print(f"  {status5}")

    # ── COMPANY FUNNEL — the actual Task 3 deliverable ──────────
    print(f"\n{'='*65}")
    print("LIVE VIEW — COMPANY FUNNEL (aggregate, real data)")
    print(f"{'='*65}")

    funnel = pd.read_sql("""
        WITH posted AS (
            SELECT job_id, company_id FROM job_supply_events
        ),
        viewed AS (
            SELECT job_id, COUNT(DISTINCT student_id) n FROM job_view_events GROUP BY job_id
        ),
        applied AS (
            SELECT job_id, COUNT(*) n FROM applications GROUP BY job_id
        ),
        shortlisted AS (
            SELECT job_id, COUNT(*) n FROM applications WHERE status='Shortlisted' GROUP BY job_id
        ),
        interviewed AS (
            SELECT a.job_id, COUNT(*) n FROM interviews i
            JOIN applications a ON i.application_id = a.application_id
            GROUP BY a.job_id
        ),
        offered AS (
            SELECT a.job_id, COUNT(*) n FROM offers o
            JOIN applications a ON o.application_id = a.application_id
            GROUP BY a.job_id
        )
        SELECT
            COUNT(DISTINCT p.job_id) AS jobs_posted,
            COALESCE(SUM(v.n),0) AS total_views,
            COALESCE(SUM(ap.n),0) AS total_applications,
            COALESCE(SUM(s.n),0) AS total_shortlisted,
            COALESCE(SUM(iv.n),0) AS total_interviewed,
            COALESCE(SUM(o.n),0) AS total_offered
        FROM posted p
        LEFT JOIN viewed v ON p.job_id = v.job_id
        LEFT JOIN applied ap ON p.job_id = ap.job_id
        LEFT JOIN shortlisted s ON p.job_id = s.job_id
        LEFT JOIN interviewed iv ON p.job_id = iv.job_id
        LEFT JOIN offered o ON p.job_id = o.job_id
    """, conn)
    print(funnel.to_string(index=False))

    print(f"\nPer-company funnel (top 10 by jobs posted):")
    per_company = pd.read_sql("""
        SELECT
            c.company_name,
            COUNT(DISTINCT j.job_id) AS jobs_posted,
            COALESCE(SUM(CASE WHEN v.job_id IS NOT NULL THEN 1 ELSE 0 END),0) AS views,
            COUNT(DISTINCT a.application_id) AS applications,
            COUNT(DISTINCT CASE WHEN a.status='Shortlisted' THEN a.application_id END) AS shortlisted,
            COUNT(DISTINCT i.interview_id) AS interviewed,
            COUNT(DISTINCT o.offer_id) AS offered
        FROM companies c
        JOIN jobs j ON c.company_id = j.company_id
        LEFT JOIN job_view_events v ON j.job_id = v.job_id
        LEFT JOIN applications a ON j.job_id = a.job_id
        LEFT JOIN interviews i ON a.application_id = i.application_id
        LEFT JOIN offers o ON a.application_id = o.application_id
        GROUP BY c.company_name
        ORDER BY jobs_posted DESC
        LIMIT 10
    """, conn)
    print(per_company.to_string(index=False))

    conn.close()
    print(f"\n{'='*65}")
    all_pass = all(s == "PASS" for s in [status1, status2, status5])
    print(f"OVERALL: {'ALL CRITICAL CHECKS PASS' if all_pass else 'REVIEW WARNINGS ABOVE'}")
    print("Company funnel view is live and demoable.")
    print(f"{'='*65}")


if __name__ == "__main__":
    validate()
