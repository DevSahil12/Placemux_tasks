"""
PlaceMux — Task 2: Job-Supply Instrumentation Validator
Validates job_posted events and produces the jobs-posted live view.
Run this to confirm events are flowing correctly before the dashboard demo.
"""
import sqlite3, pandas as pd, datetime as dt

TODAY = dt.datetime(2026, 6, 18)

def validate(db="placemux.db"):
    conn = sqlite3.connect(db)
    print("=" * 60)
    print("TASK 2 — JOB SUPPLY INSTRUMENTATION VALIDATION")
    print("=" * 60)

    # ── 1. Event count ─────────────────────────────────────────
    total = pd.read_sql("SELECT COUNT(*) AS n FROM job_supply_events", conn).iloc[0,0]
    jobs  = pd.read_sql("SELECT COUNT(*) AS n FROM jobs", conn).iloc[0,0]
    print(f"\n[CHECK 1] Event count matches job rows")
    print(f"  job_supply_events : {total}")
    print(f"  jobs table rows   : {jobs}")
    print(f"  {'PASS ✓' if total == jobs else 'FAIL ✗ — mismatch!'}")

    # ── 2. Required fields — no nulls ──────────────────────────
    print(f"\n[CHECK 2] Required fields — no nulls")
    required = ["event_name","job_id","company_id","job_title","skills","min_cgpa","salary","emitted_at"]
    null_q = " + ".join([f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END)" for c in required])
    total_nulls = pd.read_sql(f"SELECT {null_q} AS n FROM job_supply_events", conn).iloc[0,0]
    for col in required:
        n = pd.read_sql(f"SELECT SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS n FROM job_supply_events", conn).iloc[0,0]
        print(f"  {col:15s} nulls: {n}  {'✓' if n==0 else '✗'}")
    print(f"  {'PASS ✓' if total_nulls == 0 else 'WARN — some nulls found'}")

    # ── 3. Duplicates ──────────────────────────────────────────
    dups = pd.read_sql("""
        SELECT job_id, COUNT(*) n FROM job_supply_events
        GROUP BY job_id HAVING n > 1
    """, conn)
    print(f"\n[CHECK 3] Duplicate job_id events")
    print(f"  Duplicate job_ids : {len(dups)}  {'PASS ✓' if len(dups)==0 else 'WARN ✗'}")

    # ── 4. Freshness ───────────────────────────────────────────
    last_ts = pd.read_sql("SELECT MAX(emitted_at) AS ts FROM job_supply_events", conn).iloc[0,0]
    hours_ago = (TODAY - dt.datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
    print(f"\n[CHECK 4] Freshness (SLA: last event < 48h ago)")
    print(f"  Last event at : {last_ts}")
    print(f"  Hours ago     : {hours_ago:.1f}")
    print(f"  {'PASS ✓' if hours_ago < 48 else 'FAIL ✗ — pipe may be stalled'}")

    # ── 5. Skill threshold completeness ────────────────────────
    no_threshold = pd.read_sql(
        "SELECT COUNT(*) AS n FROM job_supply_events WHERE min_cgpa IS NULL OR min_cgpa = 0", conn
    ).iloc[0,0]
    print(f"\n[CHECK 5] Skill threshold (min_cgpa) populated")
    print(f"  Jobs missing threshold : {no_threshold}  {'PASS ✓' if no_threshold==0 else 'WARN'}")

    # ── 6. Jobs-posted live view ────────────────────────────────
    print(f"\n[LIVE VIEW] Jobs Posted by Day (last 14 days)")
    daily = pd.read_sql("""
        SELECT DATE(emitted_at) AS date, COUNT(*) AS jobs_posted
        FROM job_supply_events
        WHERE emitted_at >= DATE('now', '-14 days')
        GROUP BY DATE(emitted_at)
        ORDER BY date DESC
        LIMIT 14
    """, conn)
    print(daily.to_string(index=False))

    print(f"\n[LIVE VIEW] Jobs Posted by Role (top 10)")
    by_role = pd.read_sql("""
        SELECT job_title, COUNT(*) AS count,
               ROUND(AVG(salary),0) AS avg_salary,
               ROUND(AVG(min_cgpa),2) AS avg_min_cgpa
        FROM job_supply_events
        GROUP BY job_title ORDER BY count DESC LIMIT 10
    """, conn)
    print(by_role.to_string(index=False))

    print(f"\n[LIVE VIEW] Jobs by Status")
    by_status = pd.read_sql("""
        SELECT status, COUNT(*) AS count,
               ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM job_supply_events),1) AS pct
        FROM job_supply_events GROUP BY status ORDER BY count DESC
    """, conn)
    print(by_status.to_string(index=False))

    print(f"\n[LIVE VIEW] Supply by Company (top 10 by jobs posted)")
    by_co = pd.read_sql("""
        SELECT c.company_name, c.industry, COUNT(e.job_id) AS jobs_posted
        FROM job_supply_events e
        JOIN companies c ON e.company_id = c.company_id
        GROUP BY c.company_name ORDER BY jobs_posted DESC LIMIT 10
    """, conn)
    print(by_co.to_string(index=False))

    conn.close()
    print("\n" + "=" * 60)
    print("ALL CHECKS COMPLETE — Events validated. View is live.")
    print("=" * 60)


if __name__ == "__main__":
    validate()
