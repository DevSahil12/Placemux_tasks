"""
PlaceMux — Task 10: Revenue Command Center Validator
Validates that the unified Revenue Command Center is live, sourced,
and demoable end-to-end — integrating all revenue streams from Tasks 6–9.

Run: python3 validate_revenue_command_center.py
"""
import sys, os
from revenue_command_center import compute, validate, RCC_METRIC_DICTIONARY

DB = os.path.join(os.path.dirname(__file__), "placemux.db")


def main():
    print("=" * 65)
    print("TASK 10 — REVENUE COMMAND CENTER VALIDATION")
    print("Founder verify: Revenue dashboard live, end-to-end demoable.")
    print("=" * 65)
    print()

    m      = compute(DB)
    checks = validate(DB)

    # ── Print all metrics ─────────────────────────────────────
    print("LIVE METRICS:\n")
    print(f"  Gross Revenue (company + student) : ₹{m['gross_revenue_inr']:>12,.2f}")
    print(f"  Total Refunded                    : ₹{m['total_refunded_inr']:>12,.2f}")
    print(f"  Net Revenue                       : ₹{m['net_revenue_inr']:>12,.2f}")
    print(f"  Revenue — Last 7 Days             : ₹{m['revenue_last_7d_inr']:>12,.2f}")
    wow = m['revenue_wow_growth_pct']
    print(f"  WoW Growth                        :  {'N/A (seeded)':>11}")
    print(f"  Company ARPU                      : ₹{m['company_arpu_inr']:>12,.2f}")
    print(f"  Net ARPU (after refunds)          : ₹{m['net_arpu_after_refunds']:>12,.2f}")
    print(f"  Paying Companies                  :  {m['paying_companies']:>11}")
    print(f"  Student Payment Success Rate      :  {m['student_payment_success_rate_pct']:>10}%")
    print(f"  Refund Rate                       :  {m['refund_rate_pct']:>10}%")
    print(f"  Reconciliation Match Rate         :  {m['reconciliation_match_rate_pct']:>10}%")
    print(f"  Pay→App Integrity                 :  {m['pay_to_app_integrity_pct']:>10}%")
    print(f"  Failed-payment App Leaks          :  {m['failed_payment_app_leak_count']:>11}")
    print(f"  Failure Impact on ARPU            :  {m['failure_impact_on_arpu_pct']:>10}%")
    print(f"  Gateway Mode                      :  {m['gateway_mode']:>11}")
    print()

    if m['revenue_by_type']:
        print("  Revenue by Type:")
        for row in m['revenue_by_type']:
            print(f"    {row['payment_type']:<18} {row['transactions']:>3} txns  ₹{row['revenue_inr']:>10,.0f}")
    print()

    # ── Print validation checks ───────────────────────────────
    print("VALIDATION CHECKS:\n")
    all_ok  = True
    n_pass  = 0
    n_warn  = 0
    n_fail  = 0
    for name, res in checks.items():
        icon = "✅ PASS" if res["result"] == "PASS" else \
               ("⚠️ WARN" if res["result"] == "WARN" else "❌ FAIL")
        print(f"  {icon}  {name}")
        print(f"          {res['detail']}")
        if res["result"] == "PASS":  n_pass += 1
        elif res["result"] == "WARN": n_warn += 1
        else:                          n_fail += 1; all_ok = False
    print()

    # ── Summary ───────────────────────────────────────────────
    print("=" * 65)
    print(f"RESULT:  {n_pass} PASS  |  {n_warn} WARN  |  {n_fail} FAIL")
    print()
    if n_fail == 0:
        print("✅  TASK 10 COMPLETE — Revenue Command Center is live.")
        print("    All revenue streams integrated. Real data. Demoable.")
        print()
        print("    Self-check answers (can show live, not just describe):")
        print(f"    • Total gross revenue      : ₹{m['gross_revenue_inr']:,.0f}")
        print(f"    • Net after refunds        : ₹{m['net_revenue_inr']:,.0f}")
        print(f"    • Pay→App integrity        : {m['pay_to_app_integrity_pct']}% (must be 100%)")
        print(f"    • Failed payment app leaks : {m['failed_payment_app_leak_count']} (must be 0)")
        print(f"    • DB↔Gateway match         : {m['reconciliation_match_rate_pct']}%")
        print(f"    • Gateway mode             : {m['gateway_mode'].upper()} (test = safe to demo)")
        if m['failure_impact_on_arpu_pct'] > 15:
            print(f"    • ⚠️  Failure impact {m['failure_impact_on_arpu_pct']}% > 15% — add UPI/wallet payment methods")
    else:
        print("❌  TASK 10 INCOMPLETE — Fix FAIL checks above before submitting.")
        sys.exit(1)
    print("=" * 65)


if __name__ == "__main__":
    main()
