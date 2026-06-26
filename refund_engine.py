"""
PlaceMux — Task 8: Refund/Failure Analytics Engine
Receipts, Refunds & Reconciliation

Every metric shows: definition, formula, source, decision, expected range.
Imported by dashboard.py and validate_refund_analytics.py.
"""
import sqlite3, os, datetime as dt

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

REFUND_METRIC_DICTIONARY = {
    "total_receipts_issued": {
        "definition": "Total receipts issued across company + student payments.",
        "formula": "COUNT(*) FROM receipts",
        "source": "receipts",
        "decision": "Should equal total successful payments. Any gap = a receipt "
                    "generation bug — customer paid but has no proof.",
        "expected_range": "= COUNT(payments WHERE status='success') + "
                          "COUNT(student_payments WHERE status='success')",
    },
    "receipt_coverage_rate": {
        "definition": "% of successful payments that have a receipt. Should be 100%.",
        "formula": "COUNT(receipts) / (COUNT(payments success) + "
                   "COUNT(student_payments success)) × 100",
        "source": "receipts, payments, student_payments",
        "decision": "Any value < 100% → receipt generation pipeline has a bug → "
                    "fix before real money goes live. Customers cannot be refunded "
                    "without a receipt.",
        "expected_range": "100% (integrity check)",
    },
    "total_refunds_issued": {
        "definition": "Total refund transactions initiated.",
        "formula": "COUNT(*) FROM refunds",
        "source": "refunds",
        "decision": "Track volume weekly. Spike → investigate reason breakdown first.",
        "expected_range": "< 15% of receipts",
    },
    "refund_rate": {
        "definition": "% of receipts that resulted in a refund.",
        "formula": "COUNT(refunds) / COUNT(receipts) × 100",
        "source": "refunds, receipts",
        "decision": "> 15% → product or payment flow has a systemic problem. "
                    "Diagnose by reason_breakdown before taking any action.",
        "expected_range": "5–12%",
    },
    "refund_success_rate": {
        "definition": "% of initiated refunds that the gateway successfully processed.",
        "formula": "COUNT(refunds WHERE status='processed') / COUNT(refunds) × 100",
        "source": "refunds",
        "decision": "< 90% → gateway refund pipeline is unreliable → "
                    "escalate to payment team. Failed refunds must be retried "
                    "manually — customer is waiting for money.",
        "expected_range": "90–98%",
    },
    "total_refunded_inr": {
        "definition": "Total INR refunded to customers (company + student combined).",
        "formula": "SUM(amount_inr) FROM refunds WHERE status='processed'",
        "source": "refunds WHERE status='processed'",
        "decision": "Compare against total_revenue_inr to compute net revenue. "
                    "Rising refunded_inr with flat refund_count = larger refunds "
                    "being issued (subscription cancellations, not small failures).",
        "expected_range": "< 12% of gross revenue",
    },
    "refund_by_reason": {
        "definition": "Refund count and amount broken down by reason.",
        "formula": "COUNT(*), SUM(amount_inr) FROM refunds GROUP BY reason",
        "source": "refunds.reason",
        "decision": "Dominant reason tells you exactly what to fix: "
                    "candidate_withdrew → improve candidate commitment UX; "
                    "company_cancelled → add job-posting commitment policy; "
                    "gateway_error → infra issue with payment provider; "
                    "duplicate_transaction → add idempotency key.",
        "expected_range": "No single reason > 40%",
    },
    "refund_by_source": {
        "definition": "Refunds split by payment source: company vs student.",
        "formula": "COUNT(*), SUM(amount_inr) FROM refunds GROUP BY payment_source",
        "source": "refunds.payment_source",
        "decision": "Student refund rate rising → conversion flow has friction. "
                    "Company refund rate rising → supply-side commitment problem.",
        "expected_range": "Both sources present and trackable",
    },
    "avg_refund_processing_time_hours": {
        "definition": "Average hours from refund_initiated to refund_processed.",
        "formula": "AVG((JULIANDAY(processed_at) - JULIANDAY(initiated_at)) × 24) "
                   "FROM refunds WHERE status='processed'",
        "source": "refunds WHERE status='processed'",
        "decision": "> 24h → gateway SLA is being missed → customer is waiting "
                    "too long for their money back, increasing support load.",
        "expected_range": "< 24 hours (T+1 settlement)",
    },
    "failed_refunds_needing_retry": {
        "definition": "Count of refunds that failed at the gateway and need manual retry.",
        "formula": "COUNT(*) FROM refunds WHERE status='failed'",
        "source": "refunds WHERE status='failed'",
        "decision": "Each one is a customer waiting for money. "
                    "Should be actioned within 24h — export this list daily "
                    "and hand to the payment team.",
        "expected_range": "0 ideally, action any > 0 within 24h",
    },
    "reconciliation_match_rate": {
        "definition": "% of daily reconciliation runs where our records "
                       "exactly matched the gateway.",
        "formula": "SUM(matched) / COUNT(*) × 100 FROM payment_reconciliation",
        "source": "payment_reconciliation",
        "decision": "Any unmatched day → do not wait. Investigate with gateway "
                    "before end of day. Discrepancies compound and become "
                    "harder to trace after 48h.",
        "expected_range": "100% (any < 100% = investigate immediately)",
    },
    "net_revenue_inr": {
        "definition": "Gross revenue minus total refunds processed.",
        "formula": "SUM(payments success amount) + SUM(student_payments success amount) "
                   "- SUM(refunds processed amount)",
        "source": "payments, student_payments, refunds",
        "decision": "The single bottom-line revenue number. Use this, not gross, "
                    "for any financial reporting or founder update.",
        "expected_range": "Gross revenue × (1 - refund_rate)",
    },
}


def compute(db=DB) -> dict:
    conn = sqlite3.connect(db)
    c    = conn.cursor()
    m    = {}

    # receipt coverage
    n_receipts  = c.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    n_co_succ   = c.execute("SELECT COUNT(*) FROM payments WHERE status='success'").fetchone()[0]
    n_st_succ   = c.execute("SELECT COUNT(*) FROM student_payments WHERE status='success'").fetchone()[0]
    total_succ  = n_co_succ + n_st_succ

    m["total_receipts_issued"]   = n_receipts
    m["receipt_coverage_rate"]   = round(n_receipts / max(total_succ,1) * 100, 1)

    # refund volume
    n_refunds   = c.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
    n_processed = c.execute("SELECT COUNT(*) FROM refunds WHERE status='processed'").fetchone()[0]
    n_failed_r  = c.execute("SELECT COUNT(*) FROM refunds WHERE status='failed'").fetchone()[0]

    m["total_refunds_issued"]          = n_refunds
    m["refund_rate"]                   = round(n_refunds / max(n_receipts,1) * 100, 1)
    m["refund_success_rate"]           = round(n_processed / max(n_refunds,1) * 100, 1)
    m["failed_refunds_needing_retry"]  = n_failed_r

    # refund amounts
    total_refunded = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM refunds WHERE status='processed'"
    ).fetchone()[0]
    m["total_refunded_inr"] = round(total_refunded, 2)

    # net revenue
    gross_co  = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='success'"
    ).fetchone()[0]
    gross_st  = c.execute(
        "SELECT COALESCE(SUM(amount_inr),0) FROM student_payments WHERE status='success'"
    ).fetchone()[0]
    m["net_revenue_inr"] = round(gross_co + gross_st - total_refunded, 2)

    # refund by reason
    reasons = c.execute("""
        SELECT reason, COUNT(*) n, ROUND(SUM(amount_inr),2) total_inr
        FROM refunds GROUP BY reason ORDER BY n DESC
    """).fetchall()
    m["refund_by_reason"] = {r[0]: {"count": r[1], "total_inr": r[2]} for r in reasons}

    # refund by source
    sources = c.execute("""
        SELECT payment_source, COUNT(*) n, ROUND(SUM(amount_inr),2) total_inr
        FROM refunds GROUP BY payment_source
    """).fetchall()
    m["refund_by_source"] = {r[0]: {"count": r[1], "total_inr": r[2]} for r in sources}

    # avg processing time
    avg_h = c.execute("""
        SELECT AVG((JULIANDAY(processed_at) - JULIANDAY(initiated_at)) * 24)
        FROM refunds WHERE status='processed'
    """).fetchone()[0]
    m["avg_refund_processing_time_hours"] = round(avg_h, 2) if avg_h else None

    # reconciliation
    recon = c.execute(
        "SELECT SUM(matched), COUNT(*) FROM payment_reconciliation"
    ).fetchone()
    m["reconciliation_match_rate"] = round(
        recon[0] / max(recon[1],1) * 100, 1) if recon[1] else None

    conn.close()
    return m


def get_failed_refunds(db=DB) -> list:
    """Returns real failed refund rows — shown in dashboard to prove retry list is real."""
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT r.refund_id, r.receipt_id, rc.receipt_number,
               r.payment_source, r.amount_inr, r.reason,
               r.initiated_by, r.initiated_at, r.status
        FROM refunds r JOIN receipts rc ON r.receipt_id = rc.receipt_id
        WHERE r.status = 'failed'
        ORDER BY r.initiated_at DESC LIMIT 10
    """).fetchall()
    conn.close()
    return [{"refund_id":r[0],"receipt_id":r[1],"receipt_number":r[2],
             "source":r[3],"amount_inr":r[4],"reason":r[5],
             "initiated_by":r[6],"initiated_at":r[7],"status":r[8]}
            for r in rows]


def get_recent_receipts(db=DB, limit=10) -> list:
    """Returns recent receipts for the receipts ledger view."""
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT receipt_number, payment_source, amount_inr,
               payment_type, issued_at, refund_eligible
        FROM receipts ORDER BY receipt_id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"receipt_number":r[0],"source":r[1],"amount_inr":r[2],
             "type":r[3],"issued_at":r[4],"refund_eligible":r[5]}
            for r in rows]


if __name__ == "__main__":
    m = compute()
    print("=" * 65)
    print("PLACEMUX — TASK 8 REFUND/FAILURE ANALYTICS METRICS")
    print("=" * 65)
    for k, v in m.items():
        defn = REFUND_METRIC_DICTIONARY.get(k, {})
        print(f"\n  {k}")
        print(f"    Value    : {v}")
        print(f"    Formula  : {defn.get('formula','—')}")
        print(f"    Decision : {defn.get('decision','—')[:80]}")
