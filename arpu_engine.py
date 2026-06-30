"""
PlaceMux — Task 9: ARPU + Cohort Revenue Engine
Failure Handling & Resilience — Deepen Revenue Views

Computes:
  1. ARPU (Average Revenue Per User) — company-side and student-side
  2. Cohort revenue — revenue grouped by company signup week/month
  3. Revenue trend — daily/weekly revenue over time
  4. Failure resilience metrics — how payment failures affect revenue cohorts
  5. Cohort retention — which signup cohorts keep paying over time

No new tables — everything computed from:
  payments, student_payments, companies, students, receipts, refunds

Every metric shows: definition, formula, source, decision, expected range.
"""

import sqlite3, os, datetime as dt
from collections import defaultdict

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

ARPU_METRIC_DICTIONARY = {
    "arpu_company_inr": {
        "definition": "Average Revenue Per Company — total company-side revenue "
                      "divided by distinct paying companies.",
        "formula": "SUM(amount_inr) / COUNT(DISTINCT company_id) "
                   "FROM payments WHERE status='success'",
        "source": "payments WHERE status='success'",
        "decision": "Rising ARPU with flat company count → upsell/cross-sell working. "
                    "Flat ARPU with rising company count → growth is wide not deep → "
                    "introduce higher-tier plans or per-shortlist upsell.",
        "expected_range": "₹8,000–₹15,000 per company at launch",
    },
    "arpu_student_inr": {
        "definition": "Average Revenue Per Student — total student ₹100 fees "
                      "divided by distinct paying students.",
        "formula": "SUM(amount_inr) / COUNT(DISTINCT student_id) "
                   "FROM student_payments WHERE status='success'",
        "source": "student_payments WHERE status='success'",
        "decision": "Low ARPU with high student count → students apply once and leave → "
                    "investigate whether shortlisting is happening fast enough to "
                    "motivate repeat applications.",
        "expected_range": "₹100–₹300 per student (1–3 applications average)",
    },
    "arpu_blended_inr": {
        "definition": "Blended ARPU across both company and student revenue streams, "
                      "per total unique payers.",
        "formula": "(SUM(company payments) + SUM(student payments)) / "
                   "(COUNT(DISTINCT companies) + COUNT(DISTINCT students))",
        "source": "payments + student_payments WHERE status='success'",
        "decision": "The single revenue-per-payer number for investor reporting. "
                    "Compare month-over-month to track monetisation efficiency.",
        "expected_range": "Weighted by mix of company vs student payers",
    },
    "revenue_per_job_posted": {
        "definition": "Average revenue generated per job posting "
                      "(job_slot fee + shortlist fees for that job).",
        "formula": "SUM(amount_inr) / COUNT(DISTINCT job_id) "
                   "FROM payments WHERE status='success'",
        "source": "payments WHERE status='success' AND job_id IS NOT NULL",
        "decision": "Low revenue-per-job → per_shortlist payments are not converting → "
                    "either shortlisting rate is low or companies avoid the fee model.",
        "expected_range": "₹4,000–₹8,000 per job (slot + shortlists)",
    },
    "cohort_revenue_by_signup_week": {
        "definition": "Total revenue grouped by the week the paying company signed up. "
                      "Shows which acquisition cohorts monetise best.",
        "formula": "SUM(p.amount_inr) GROUP BY strftime('%Y-W%W', c.created_at) "
                   "FROM payments p JOIN companies c ON p.company_id=c.company_id "
                   "WHERE p.status='success'",
        "source": "payments JOIN companies ON company_id",
        "decision": "Early cohorts with high revenue → first-mover companies are "
                    "high-value, protect them. Late cohorts with low revenue → "
                    "later acquisitons may be lower-quality → review targeting.",
        "expected_range": "Growing week-over-week in a healthy marketplace",
    },
    "weekly_revenue_trend": {
        "definition": "Total revenue (company + student) grouped by calendar week.",
        "formula": "SUM(amount_inr) GROUP BY strftime('%Y-W%W', resolved_at) "
                   "FROM payments UNION student_payments WHERE status='success'",
        "source": "payments + student_payments WHERE status='success'",
        "decision": "Flat or declining weekly trend = growth has stalled → "
                    "founder should investigate supply (new jobs) vs demand "
                    "(new students) separately to isolate the cause.",
        "expected_range": "Growing week-over-week pre-launch",
    },
    "failure_impact_on_arpu": {
        "definition": "Revenue lost to payment failures as a % of attempted revenue. "
                      "Shows how much ARPU is being suppressed by payment friction.",
        "formula": "SUM(amount_inr WHERE status='failed') / "
                   "SUM(amount_inr WHERE status IN ('success','failed')) × 100",
        "source": "payments + student_payments",
        "decision": "> 15% → payment friction is a significant ARPU suppressor → "
                    "add alternative payment methods (UPI, wallet) before "
                    "investing in acquisition.",
        "expected_range": "< 15% (acceptable payment friction at launch)",
    },
    "cohort_repeat_payment_rate": {
        "definition": "% of companies that made more than one successful payment "
                      "(indicating retention and repeat engagement).",
        "formula": "COUNT(company_id WHERE payment_count > 1) / "
                   "COUNT(DISTINCT company_id) × 100 "
                   "FROM payments WHERE status='success'",
        "source": "payments WHERE status='success'",
        "decision": "Low repeat rate → companies post one job and leave → "
                    "investigate whether the hire was made (good churn) or "
                    "the product disappointed (bad churn).",
        "expected_range": "> 40% repeat payment rate indicates healthy retention",
    },
    "revenue_by_industry_cohort": {
        "definition": "Revenue breakdown by company industry. "
                      "Shows which industry cohorts contribute most.",
        "formula": "SUM(p.amount_inr) GROUP BY c.industry "
                   "FROM payments p JOIN companies c ON p.company_id=c.company_id "
                   "WHERE p.status='success'",
        "source": "payments JOIN companies ON company_id",
        "decision": "High revenue from one industry → invest in that vertical. "
                    "Low revenue from a targeted industry → review whether the "
                    "product fits that segment's hiring workflow.",
        "expected_range": "Spread across industries; no single industry > 40%",
    },
    "net_arpu_after_refunds": {
        "definition": "ARPU adjusted for refunds — the true average revenue per "
                      "paying company after deducting refunds.",
        "formula": "(SUM(payments success) - SUM(refunds processed)) / "
                   "COUNT(DISTINCT paying company_id)",
        "source": "payments + refunds",
        "decision": "If net_arpu drops significantly below gross_arpu → refund rate "
                    "is eroding per-company value → target the refund reasons "
                    "causing the biggest ARPU drag.",
        "expected_range": "Within 10% of gross ARPU at launch",
    },
}


def compute(db=DB) -> dict:
    conn = sqlite3.connect(db)
    c    = conn.cursor()
    m    = {}

    # ── ARPU metrics ─────────────────────────────────────────────────────
    co_rev = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0), COUNT(DISTINCT company_id) "
        "FROM payments WHERE status='success'"
    ).fetchone()
    m["arpu_company_inr"] = round(co_rev[0] / max(co_rev[1],1), 2)

    st_rev = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0), COUNT(DISTINCT student_id) "
        "FROM student_payments WHERE status='success'"
    ).fetchone()
    m["arpu_student_inr"] = round(st_rev[0] / max(st_rev[1],1), 2)

    total_rev  = co_rev[0] + st_rev[0]
    total_payers = co_rev[1] + st_rev[1]
    m["arpu_blended_inr"] = round(total_rev / max(total_payers,1), 2)

    rev_per_job = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0), COUNT(DISTINCT job_id) "
        "FROM payments WHERE status='success' AND job_id IS NOT NULL"
    ).fetchone()
    m["revenue_per_job_posted"] = round(rev_per_job[0] / max(rev_per_job[1],1), 2)

    # ── Cohort revenue by signup week ────────────────────────────────────
    cohort_rows = c.execute("""
        SELECT
            strftime('%Y-W%W', c.created_at) AS signup_week,
            COUNT(DISTINCT p.company_id)      AS paying_companies,
            ROUND(SUM(p.amount_inr), 2)       AS cohort_revenue,
            ROUND(SUM(p.amount_inr)/COUNT(DISTINCT p.company_id), 2) AS cohort_arpu
        FROM payments p
        JOIN companies c ON p.company_id = c.company_id
        WHERE p.status = 'success'
        GROUP BY signup_week
        ORDER BY signup_week
    """).fetchall()
    m["cohort_revenue_by_signup_week"] = [
        {"week": r[0], "companies": r[1],
         "revenue_inr": r[2], "arpu_inr": r[3]}
        for r in cohort_rows
    ]

    # ── Weekly revenue trend (company + student combined) ────────────────
    co_weekly = c.execute("""
        SELECT strftime('%Y-W%W', resolved_at) wk,
               ROUND(SUM(amount_inr),2) rev
        FROM payments WHERE status='success' AND resolved_at IS NOT NULL
        GROUP BY wk ORDER BY wk
    """).fetchall()
    st_weekly = c.execute("""
        SELECT strftime('%Y-W%W', resolved_at) wk,
               ROUND(SUM(amount_inr),2) rev
        FROM student_payments WHERE status='success' AND resolved_at IS NOT NULL
        GROUP BY wk ORDER BY wk
    """).fetchall()
    combined = defaultdict(float)
    for wk, rev in co_weekly:
        combined[wk] += rev
    for wk, rev in st_weekly:
        combined[wk] += rev
    m["weekly_revenue_trend"] = [
        {"week": wk, "revenue_inr": round(rev, 2)}
        for wk, rev in sorted(combined.items())
    ]

    # ── Failure impact on ARPU ───────────────────────────────────────────
    co_fail = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='failed'"
    ).fetchone()[0]
    st_fail = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM student_payments WHERE status='failed'"
    ).fetchone()[0]
    attempted = total_rev + co_fail + st_fail
    m["failure_impact_on_arpu"] = round(
        (co_fail + st_fail) / max(attempted,1) * 100, 1)

    # ── Cohort repeat payment rate ───────────────────────────────────────
    repeat = c.execute("""
        SELECT COUNT(*) FROM (
            SELECT company_id FROM payments WHERE status='success'
            GROUP BY company_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    total_co_payers = co_rev[1]
    m["cohort_repeat_payment_rate"] = round(
        repeat / max(total_co_payers,1) * 100, 1)

    # ── Revenue by industry cohort ───────────────────────────────────────
    industry_rows = c.execute("""
        SELECT c.industry,
               COUNT(DISTINCT p.company_id) companies,
               ROUND(SUM(p.amount_inr),2) revenue_inr,
               ROUND(SUM(p.amount_inr)/COUNT(DISTINCT p.company_id),2) arpu_inr
        FROM payments p
        JOIN companies c ON p.company_id = c.company_id
        WHERE p.status = 'success'
        GROUP BY c.industry
        ORDER BY revenue_inr DESC
    """).fetchall()
    m["revenue_by_industry_cohort"] = [
        {"industry": r[0], "companies": r[1],
         "revenue_inr": r[2], "arpu_inr": r[3]}
        for r in industry_rows
    ]

    # ── Net ARPU after refunds ───────────────────────────────────────────
    total_refunded = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM refunds WHERE status='processed'"
    ).fetchone()[0]
    net_co_rev = co_rev[0] - total_refunded
    m["net_arpu_after_refunds"] = round(net_co_rev / max(co_rev[1],1), 2)

    # ── Daily revenue (last 30 days) for trend chart ─────────────────────
    daily = c.execute("""
        SELECT DATE(resolved_at) d, ROUND(SUM(amount_inr),2) rev,
               'company' src
        FROM payments WHERE status='success' AND resolved_at IS NOT NULL
        GROUP BY d
        UNION ALL
        SELECT DATE(resolved_at) d, ROUND(SUM(amount_inr),2) rev,
               'student' src
        FROM student_payments WHERE status='success' AND resolved_at IS NOT NULL
        GROUP BY d
        ORDER BY d
    """).fetchall()
    m["_daily_revenue"] = [
        {"date": r[0], "revenue_inr": r[1], "source": r[2]} for r in daily]

    # ── Cohort ARPU by company age band ──────────────────────────────────
    age_band = c.execute("""
        SELECT
            CASE
                WHEN (JULIANDAY('now') - JULIANDAY(c.created_at)) <= 30
                    THEN '0-30 days'
                WHEN (JULIANDAY('now') - JULIANDAY(c.created_at)) <= 60
                    THEN '31-60 days'
                ELSE '60+ days'
            END AS age_band,
            COUNT(DISTINCT p.company_id) companies,
            ROUND(SUM(p.amount_inr),2) revenue_inr,
            ROUND(SUM(p.amount_inr)/COUNT(DISTINCT p.company_id),2) arpu_inr
        FROM payments p
        JOIN companies c ON p.company_id = c.company_id
        WHERE p.status = 'success'
        GROUP BY age_band ORDER BY age_band
    """).fetchall()
    m["_cohort_by_age"] = [
        {"age_band": r[0], "companies": r[1],
         "revenue_inr": r[2], "arpu_inr": r[3]}
        for r in age_band
    ]

    conn.close()
    return m


if __name__ == "__main__":
    m = compute()
    print("=" * 65)
    print("PLACEMUX — TASK 9: ARPU + COHORT REVENUE METRICS")
    print("=" * 65)
    for k, v in m.items():
        if k.startswith("_"):
            continue
        defn = ARPU_METRIC_DICTIONARY.get(k, {})
        if isinstance(v, list):
            print(f"\n  {k}: {len(v)} rows")
            for row in v[:3]:
                print(f"    {row}")
        else:
            print(f"\n  {k}: {v}")
            if defn.get("formula"):
                print(f"    Formula  : {defn['formula'][:80]}")
                print(f"    Decision : {defn['decision'][:80]}")
