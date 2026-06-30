"""
PlaceMux — Liquidity Dashboard Metric Engine
Task 5 · Week 2 · Phase 2 · Marketplace Integration & Company Portal v1

This is the single computation layer for the marketplace liquidity dashboard.
Every metric below:
  - traces back to a real event table (source)
  - forwards to a decision the founder would actually make
  - is independently queryable so the dashboard can explain each number on the spot

"End-to-end: company posts → student applies → company shortlists."
The Liquidity Index at the bottom is the composite number that tells the founder
whether the marketplace is healthy enough at launch.
"""

import sqlite3, datetime as dt, os

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

METRIC_DICTIONARY = {
    # ── SUPPLY SIDE (Task 2) ──────────────────────────────────────────────
    "active_listings": {
        "definition": "Jobs currently posted and not yet filled or expired.",
        "source": "job_supply_events",
        "decision": "If dropping week-over-week, sales/onboarding pipeline is slowing "
                    "— act on supply acquisition before it hits the candidate experience.",
    },
    "jobs_posted_last_7d": {
        "definition": "Count of job_posted events in the last 7 days.",
        "source": "job_supply_events",
        "decision": "Week-on-week growth tells the founder whether supply-side momentum "
                    "is building or stalling — informs whether to invest in outreach.",
    },
    "avg_min_cgpa_threshold": {
        "definition": "Average minimum CGPA threshold set across all active jobs.",
        "source": "job_supply_events",
        "decision": "Rising threshold tightens the candidate pool — "
                    "if verification_pass_rate drops simultaneously, threshold is the cause.",
    },
    "supply_growth_wow": {
        "definition": "Week-over-week % change in jobs posted.",
        "source": "job_supply_events",
        "decision": "Negative WoW → supply shrinking → founder should investigate "
                    "company churn or posting friction before scaling marketing.",
    },

    # ── DISCOVERY (Task 3) ────────────────────────────────────────────────
    "search_to_view_rate": {
        "definition": "% of searches where the student clicked through to view a job.",
        "source": "job_search_events + job_view_events",
        "decision": "< 30% → ranking/relevance is broken → fix before spending on "
                    "candidate acquisition, or acquisition spend is wasted.",
    },
    "search_latency_p95": {
        "definition": "95th-percentile search response latency in milliseconds.",
        "source": "job_search_events",
        "decision": "> 500ms → discovery feels broken from day one → "
                    "escalate to backend as a launch blocker, not a 'later' fix.",
    },
    "zero_result_rate": {
        "definition": "% of searches returning 0 results.",
        "source": "job_search_events",
        "decision": "High rate signals a supply gap in specific role categories → "
                    "direct sales outreach at those categories specifically.",
    },
    "avg_fit_score": {
        "definition": "Average fit score (0-100) of jobs surfaced in search results.",
        "source": "job_search_events",
        "decision": "Low average fit → matching algorithm needs tuning or supply "
                    "doesn't match the skills being searched.",
    },

    # ── APPLICATION FUNNEL (Task 4) ───────────────────────────────────────
    "verification_pass_rate": {
        "definition": "% of submitted applications where the student met the job's min_cgpa.",
        "source": "applications (verified column)",
        "decision": "Low rate → search is surfacing jobs to unqualified students → "
                    "fix fit-ranking filter, not the threshold.",
    },
    "apply_to_shortlist_rate": {
        "definition": "% of verified applications that got shortlisted.",
        "source": "applications",
        "decision": "Low rate → company's expectations may be misaligned with the "
                    "available verified pool → prompt company to review job description.",
    },
    "shortlist_to_interview_rate": {
        "definition": "% of shortlisted applications that progressed to interview.",
        "source": "applications + interviews",
        "decision": "Stall here → company is shortlisting but not following through → "
                    "nudge company or flag job as stale.",
    },
    "interview_to_offer_rate": {
        "definition": "% of interviewed candidates who received an offer.",
        "source": "interviews + offers",
        "decision": "Low rate → interview process or offer competitiveness is the "
                    "bottleneck, not the application pool.",
    },
    "shortlist_integrity": {
        "definition": "% of shortlisted applications that were verified (should always be 100%).",
        "source": "applications",
        "decision": "Any value below 100% → data/process integrity failure → "
                    "halt and investigate immediately before trusting any funnel numbers.",
    },

    # ── COMPOSITE ─────────────────────────────────────────────────────────
    "liquidity_index": {
        "definition": "Composite 0-100 score: 35% fill-proxy (apply_to_shortlist_rate) "
                       "+ 30% supply health (active_listings normalised) "
                       "+ 20% discovery (search_to_view_rate) "
                       "+ 15% verification quality (verification_pass_rate). "
                       "Each component is normalised to 0-100 before weighting.",
        "source": "job_supply_events + job_search_events + job_view_events + applications",
        "decision": "The single number a founder checks each morning. "
                    "> 70 → marketplace healthy, keep onboarding companies. "
                    "50-70 → monitor closely, one stage is underperforming. "
                    "< 50 → pause new company onboarding, diagnose the weakest component first.",
    },
}


def _norm(val, lo, hi):
    """Normalise val to 0-100 given expected range [lo, hi]."""
    if val is None:
        return 0.0
    return max(0.0, min(100.0, (val - lo) / max(hi - lo, 0.0001) * 100))


def compute(db=DB) -> dict:
    conn = sqlite3.connect(db)
    c    = conn.cursor()
    now  = dt.datetime.now()
    ago7 = (now - dt.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    ago14= (now - dt.timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    m = {}

    # ── supply ────────────────────────────────────────────────────────────
    m["active_listings"] = c.execute(
        "SELECT COUNT(*) FROM jobs WHERE status='open'"
    ).fetchone()[0]

    m["jobs_posted_last_7d"] = c.execute(
        "SELECT COUNT(*) FROM job_supply_events WHERE emitted_at >= ?", (ago7,)
    ).fetchone()[0]

    m["avg_min_cgpa_threshold"] = round(
        c.execute("SELECT AVG(min_cgpa) FROM job_supply_events WHERE status='open'").fetchone()[0] or 0, 2
    )

    last7  = c.execute("SELECT COUNT(*) FROM job_supply_events WHERE emitted_at >= ?", (ago7,)).fetchone()[0]
    prior7 = c.execute("SELECT COUNT(*) FROM job_supply_events WHERE emitted_at >= ? AND emitted_at < ?",
                       (ago14, ago7)).fetchone()[0]
    if prior7 == 0:
        m["supply_growth_wow"] = None   # not enough history yet — show as N/A, not ∞
    else:
        m["supply_growth_wow"] = round((last7 - prior7) / prior7 * 100, 1)

    # ── discovery ────────────────────────────────────────────────────────
    total_searches = c.execute("SELECT COUNT(*) FROM job_search_events").fetchone()[0]
    searches_with_click = c.execute(
        "SELECT COUNT(*) FROM job_search_events WHERE clicked_job_id IS NOT NULL"
    ).fetchone()[0]
    m["search_to_view_rate"] = round(searches_with_click / max(total_searches, 1) * 100, 1)

    latency_row = c.execute(
        "SELECT latency_ms FROM job_search_events WHERE latency_ms IS NOT NULL ORDER BY latency_ms"
    ).fetchall()
    if latency_row:
        p95_idx = int(len(latency_row) * 0.95)
        m["search_latency_p95"] = latency_row[min(p95_idx, len(latency_row)-1)][0]
    else:
        m["search_latency_p95"] = None

    m["zero_result_rate"] = round(
        c.execute("SELECT AVG(CASE WHEN result_count=0 THEN 1.0 ELSE 0.0 END) FROM job_search_events").fetchone()[0] or 0,
        3
    ) * 100

    m["avg_fit_score"] = round(
        c.execute("SELECT AVG(fit_score) FROM job_search_events WHERE fit_score IS NOT NULL").fetchone()[0] or 0, 1
    )

    # ── application funnel ────────────────────────────────────────────────
    total_apps      = c.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    verified_apps   = c.execute("SELECT COUNT(*) FROM applications WHERE verified=1").fetchone()[0]
    shortlisted     = c.execute("SELECT COUNT(*) FROM applications WHERE status='Shortlisted'").fetchone()[0]
    interviewed     = c.execute("SELECT COUNT(*) FROM applications WHERE status='Interviewed'").fetchone()[0]
    offered         = c.execute("SELECT COUNT(*) FROM applications WHERE status='Offered'").fetchone()[0]
    n_interviews    = c.execute("SELECT COUNT(*) FROM interviews").fetchone()[0]
    n_offers        = c.execute("SELECT COUNT(*) FROM offers").fetchone()[0]

    # "ever shortlisted" = current Shortlisted + those that progressed further (Interviewed/Offered)
    ever_shortlisted = shortlisted + interviewed + offered
    m["verification_pass_rate"]     = round(verified_apps / max(total_apps, 1) * 100, 1)
    m["apply_to_shortlist_rate"]    = round(ever_shortlisted / max(verified_apps, 1) * 100, 1)
    m["shortlist_to_interview_rate"]= round((interviewed + offered) / max(ever_shortlisted, 1) * 100, 1)
    m["interview_to_offer_rate"]    = round(offered / max(interviewed + offered, 1) * 100, 1)

    unverified_shortlisted = c.execute(
        "SELECT COUNT(*) FROM applications WHERE status='Shortlisted' AND verified=0"
    ).fetchone()[0]
    m["shortlist_integrity"] = round(
        (shortlisted - unverified_shortlisted) / max(shortlisted, 1) * 100, 1
    )

    # ── composite liquidity index ─────────────────────────────────────────
    fill_proxy   = _norm(m["apply_to_shortlist_rate"],   0, 60)   # 35%
    supply_health= _norm(m["active_listings"],           0, 300)  # 30%
    discovery    = _norm(m["search_to_view_rate"],       0, 70)   # 20%
    verif_qual   = _norm(m["verification_pass_rate"],    0, 100)  # 15%

    m["liquidity_index"] = round(
        0.35 * fill_proxy +
        0.30 * supply_health +
        0.20 * discovery +
        0.15 * verif_qual,
        1
    )

    conn.close()
    return m


def health_status(li: float) -> tuple:
    """Returns (label, color_hex, action) for the Liquidity Index value."""
    if li >= 70:
        return "HEALTHY", "#22c55e", "Marketplace healthy — continue onboarding companies."
    elif li >= 50:
        return "MONITOR", "#f59e0b", "One stage underperforming — identify the weakest component."
    else:
        return "AT RISK", "#ef4444", "Pause new company onboarding — diagnose and fix weakest component first."


if __name__ == "__main__":
    metrics = compute()
    print("=" * 60)
    print("PLACEMUX — LIQUIDITY DASHBOARD METRICS")
    print("=" * 60)
    for k, v in metrics.items():
        defn = METRIC_DICTIONARY.get(k, {})
        print(f"\n  {k}")
        print(f"    Value   : {v}")
        print(f"    Source  : {defn.get('source','—')}")
        print(f"    Decision: {defn.get('decision','—')[:90]}")
    li = metrics["liquidity_index"]
    label, color, action = health_status(li)
    print(f"\n{'='*60}")
    print(f"LIQUIDITY INDEX : {li}/100  [{label}]")
    print(f"ACTION          : {action}")
    print(f"{'='*60}")
