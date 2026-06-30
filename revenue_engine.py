"""
PlaceMux — Task 6: Revenue Metric Definitions
Week 3 · Phase 2 · Payments Design & Gateway Setup

Revenue model (test-mode gateway):
  per_shortlist : INR 499  — company pays each time they shortlist a verified candidate
  job_slot      : INR 1999 — company pays to post one job listing
  subscription  : INR 4999 — monthly flat fee for unlimited postings

Every metric below:
  - traces back to a real event in payment_events (source)
  - forwards to a decision the founder would actually make (decision)
  - is computable from live data with no manual steps
"""

import sqlite3, datetime as dt, os

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

REVENUE_METRIC_DICTIONARY = {
    # ── CORE REVENUE ─────────────────────────────────────────────────────
    "total_revenue_inr": {
        "definition": "Total INR collected from payment_success events (test-mode gateway).",
        "source": "payment_events WHERE event_name='payment_success'",
        "decision": "Primary revenue KPI — if flat WoW, diagnose whether supply "
                    "(fewer jobs posted) or demand (fewer shortlists) is the cause.",
    },
    "revenue_last_7d": {
        "definition": "INR collected from payment_success events in the last 7 days.",
        "source": "payment_events WHERE event_name='payment_success'",
        "decision": "Trailing-7d revenue is the founder's weekly health check — "
                    "decline triggers investigation before month-end reporting.",
    },
    "revenue_wow_growth": {
        "definition": "Week-over-week % change in revenue collected.",
        "source": "payment_events",
        "decision": "Negative WoW → revenue contracting → compare with supply_growth_wow "
                    "to distinguish a market problem from a payment friction problem.",
    },
    "revenue_by_type": {
        "definition": "INR breakdown: per_shortlist vs job_slot vs subscription.",
        "source": "payments WHERE status='success'",
        "decision": "If per_shortlist dominates, pricing model is working as intended. "
                    "If job_slot dominates, companies are paying upfront but not "
                    "shortlisting — a quality or engagement problem, not a revenue one.",
    },

    # ── PAYMENT FUNNEL ────────────────────────────────────────────────────
    "payment_success_rate": {
        "definition": "% of initiated payments that reached payment_success status.",
        "source": "payments",
        "decision": "< 85% → gateway or UX friction is losing revenue that was "
                    "already intent-committed — fix the payment flow before scaling.",
    },
    "payment_failure_rate": {
        "definition": "% of initiated payments that reached payment_failed status.",
        "source": "payments",
        "decision": "Rising failure rate → gateway health issue or specific bank "
                    "rejecting cards → check failure_reason breakdown immediately.",
    },
    "failure_reason_breakdown": {
        "definition": "Count of payment_failed events by failure_reason.",
        "source": "payment_events WHERE event_name='payment_failed'",
        "decision": "If gateway_timeout dominates → infrastructure problem. "
                    "If card_declined dominates → pricing may be too high for the "
                    "segment or wrong payment method is being offered.",
    },
    "refund_rate": {
        "definition": "% of successful payments that were subsequently refunded.",
        "source": "payments",
        "decision": "Rising refund rate → companies are disputing charges → "
                    "review shortlist quality or clarify the per-shortlist billing model.",
    },

    # ── ARPU & MONETISATION ───────────────────────────────────────────────
    "arpc_inr": {
        "definition": "Average Revenue Per Company (INR) = total revenue / paying companies.",
        "source": "payments WHERE status='success'",
        "decision": "Low ARPC with high company count → monetisation is thin, "
                    "consider upselling subscription. High ARPC, low company count "
                    "→ concentration risk, diversify the company base.",
    },
    "paying_companies": {
        "definition": "Count of distinct companies with at least one payment_success.",
        "source": "payments WHERE status='success'",
        "decision": "This is the true monetised base — compare to total companies "
                    "to get the conversion-to-paid rate, not just signups.",
    },
    "conversion_to_paid_rate": {
        "definition": "% of all companies that have made at least one successful payment.",
        "source": "payments + companies",
        "decision": "Low rate → companies are signing up but not paying → "
                    "check whether job_slot payment is frictionless at posting time.",
    },

    # ── GATEWAY RECONCILIATION ────────────────────────────────────────────
    "gateway_mode": {
        "definition": "Current gateway mode: 'test' or 'live'.",
        "source": "payments",
        "decision": "Must be 'test' until the founder explicitly signs off on "
                    "go-live checklist. Any 'live' rows before sign-off are a critical bug.",
    },
    "unreconciled_payments": {
        "definition": "Payments with status='initiated' and no resolved_at (stuck payments).",
        "source": "payments WHERE resolved_at IS NULL AND status='initiated'",
        "decision": "Any stuck payment > 30 minutes old → gateway callback may have "
                    "failed → manual reconciliation needed before EOD to avoid "
                    "double-charging or silent revenue loss.",
    },
}


def compute_revenue(db=DB) -> dict:
    conn = sqlite3.connect(db)
    c    = conn.cursor()
    now  = dt.datetime.now()
    ago7 = (now - dt.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    ago14= (now - dt.timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")

    m = {}

    # ── core revenue ──────────────────────────────────────────────────────
    m["total_revenue_inr"] = round(
        c.execute("SELECT COALESCE(SUM(amount_inr),0) FROM payment_events WHERE event_name='payment_success'").fetchone()[0], 2)

    m["revenue_last_7d"] = round(
        c.execute("SELECT COALESCE(SUM(amount_inr),0) FROM payment_events "
                  "WHERE event_name='payment_success' AND emitted_at >= ?", (ago7,)).fetchone()[0], 2)

    last7  = c.execute("SELECT COALESCE(SUM(amount_inr),0) FROM payment_events "
                       "WHERE event_name='payment_success' AND emitted_at >= ?", (ago7,)).fetchone()[0]
    prior7 = c.execute("SELECT COALESCE(SUM(amount_inr),0) FROM payment_events "
                       "WHERE event_name='payment_success' AND emitted_at >= ? AND emitted_at < ?",
                       (ago14, ago7)).fetchone()[0]
    m["revenue_wow_growth"] = round((last7 - prior7) / max(prior7, 1) * 100, 1) if prior7 > 0 else None

    by_type = c.execute("""
        SELECT p.payment_type, ROUND(SUM(pe.amount_inr),2) revenue
        FROM payment_events pe JOIN payments p ON pe.payment_id=p.payment_id
        WHERE pe.event_name='payment_success'
        GROUP BY p.payment_type
    """).fetchall()
    m["revenue_by_type"] = {row[0]: row[1] for row in by_type}

    # ── payment funnel ────────────────────────────────────────────────────
    total_pay  = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    success    = c.execute("SELECT COUNT(*) FROM payments WHERE status='success'").fetchone()[0]
    failed     = c.execute("SELECT COUNT(*) FROM payments WHERE status='failed'").fetchone()[0]
    refunded   = c.execute("SELECT COUNT(*) FROM payments WHERE status='refunded'").fetchone()[0]

    m["payment_success_rate"] = round(success / max(total_pay, 1) * 100, 1)
    m["payment_failure_rate"] = round(failed  / max(total_pay, 1) * 100, 1)
    m["refund_rate"]          = round(refunded / max(success, 1) * 100, 1)

    reasons = c.execute("""
        SELECT failure_reason, COUNT(*) n FROM payment_events
        WHERE event_name='payment_failed' AND failure_reason IS NOT NULL
        GROUP BY failure_reason ORDER BY n DESC
    """).fetchall()
    m["failure_reason_breakdown"] = {r[0]: r[1] for r in reasons}

    # ── arpu & monetisation ────────────────────────────────────────────────
    paying_cos = c.execute(
        "SELECT COUNT(DISTINCT company_id) FROM payments WHERE status='success'"
    ).fetchone()[0]
    total_cos  = c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]

    m["paying_companies"]        = paying_cos
    m["arpc_inr"]                = round(m["total_revenue_inr"] / max(paying_cos, 1), 2)
    m["conversion_to_paid_rate"] = round(paying_cos / max(total_cos, 1) * 100, 1)

    # ── gateway reconciliation ────────────────────────────────────────────
    modes = c.execute("SELECT DISTINCT gateway_mode FROM payments").fetchall()
    m["gateway_mode"] = [r[0] for r in modes]

    stuck = c.execute("""
        SELECT COUNT(*) FROM payments
        WHERE status='initiated' AND resolved_at IS NULL
    """).fetchone()[0]
    m["unreconciled_payments"] = stuck

    conn.close()
    return m


if __name__ == "__main__":
    m = compute_revenue()
    print("=" * 65)
    print("TASK 6 — REVENUE METRIC DEFINITIONS (live values)")
    print("=" * 65)
    for k, v in m.items():
        defn = REVENUE_METRIC_DICTIONARY.get(k, {})
        print(f"\n  {k}")
        print(f"    Value   : {v}")
        print(f"    Source  : {defn.get('source','—')}")
        print(f"    Decision: {str(defn.get('decision','—'))[:90]}")
    print(f"\n{'='*65}")
    print(f"Total Revenue : INR {m['total_revenue_inr']:,.2f}")
    print(f"Success Rate  : {m['payment_success_rate']}%")
    print(f"ARPC          : INR {m['arpc_inr']:,.2f}")
    print(f"Gateway Mode  : {m['gateway_mode']}")
    print(f"{'='*65}")
