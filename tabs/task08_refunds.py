"""
Task 8 — Refund/Failure Analytics
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task08(ctx):
    """Render the "Task 8 — Refund/Failure Analytics" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    rm8 = ctx.get_refund_metrics()

    st.subheader("🔄 Refund/Failure Analytics — Receipts, Refunds & Reconciliation")
    st.caption("Every successful payment generates a receipt. "
               "Refunds are only issued against a valid receipt. "
               "Every status change is logged to refund_events (immutable audit trail).")

    # ── headline metrics ─────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Receipts Issued", f"{rm8['total_receipts_issued']:,}",
              help="Formula: COUNT(*) FROM receipts — one per successful payment")
    cov = rm8["receipt_coverage_rate"]
    c2.metric("Receipt Coverage", f"{cov}%",
              delta="100% = all payments have receipts" if cov == 100.0 else f"⚠️ Gap: {100-cov:.1f}%",
              help="Formula: COUNT(receipts)/COUNT(success payments)×100 — must be 100%")
    c3.metric("Refunds Issued", rm8["total_refunds_issued"],
              help="Formula: COUNT(*) FROM refunds")
    c4.metric("Refund Rate", f"{rm8['refund_rate']}%",
              help="Formula: COUNT(refunds)/COUNT(receipts)×100 — target < 12%")

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("Refund Success Rate", f"{rm8['refund_success_rate']}%",
              help="Formula: COUNT(status='processed')/COUNT(refunds)×100")
    c6.metric("Total Refunded", f"₹{rm8['total_refunded_inr']:,.0f}",
              help="Formula: SUM(amount_inr) FROM refunds WHERE status='processed'")
    c7.metric("Net Revenue", f"₹{rm8['net_revenue_inr']:,.0f}",
              help="Formula: gross_revenue - total_refunded_inr")
    failed_r = rm8["failed_refunds_needing_retry"]
    c8.metric("⚠️ Failed Refunds", failed_r,
              delta="Need manual retry" if failed_r > 0 else "✅ None",
              help="Formula: COUNT(*) FROM refunds WHERE status='failed'")

    st.divider()

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        # refund by reason bar chart
        reason_data = rm8.get("refund_by_reason", {})
        if reason_data:
            rdf = pd.DataFrame([
                {"Reason": k, "Count": v["count"], "Amount (₹)": v["total_inr"]}
                for k, v in reason_data.items()
            ])
            fig_r = px.bar(rdf, x="Count", y="Reason", orientation="h",
                           color="Count", color_continuous_scale="Reds",
                           title="Refunds by Reason (count)")
            fig_r.update_layout(height=320, margin=dict(t=40,b=10),
                                coloraxis_showscale=False,
                                yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_r, use_container_width=True)

    with col_r2:
        # refund by source pie
        source_data = rm8.get("refund_by_source", {})
        if source_data:
            sdf = pd.DataFrame([
                {"Source": k, "Count": v["count"], "Amount": v["total_inr"]}
                for k, v in source_data.items()
            ])
            fig_s = px.pie(sdf, names="Source", values="Amount",
                           title="Refund Amount by Source (₹)",
                           color_discrete_map={"company":"#1e2761","student":"#3b5bdb"})
            fig_s.update_layout(height=320, margin=dict(t=40,b=10))
            st.plotly_chart(fig_s, use_container_width=True)

    st.divider()

    # ── METRIC DICTIONARY ─────────────────────────────────
    st.subheader("📖 How Each Metric Is Calculated")
    for name, defn in ctx.REFUND_METRIC_DICTIONARY.items():
        val = rm8.get(name)
        if isinstance(val, dict):
            val_str = f"{len(val)} categories"
        elif isinstance(val, float):
            val_str = f"{val:.1f}"
        else:
            val_str = str(val) if val is not None else "N/A"
        with st.expander(f"**{name}** = {val_str}", expanded=False):
            st.markdown(f"**Definition:** {defn['definition']}")
            st.code(defn["formula"], language="sql")
            st.markdown(f"**Source:** `{defn['source']}`")
            st.markdown(f"**Decision:** _{defn['decision']}_")
            st.markdown(f"**Expected range:** {defn['expected_range']}")

    st.divider()

    # ── RECEIPTS LEDGER ───────────────────────────────────
    st.subheader("🧾 Recent Receipts")
    st.caption("One receipt issued per successful payment. "
               "receipt_number = human-readable proof. "
               "refund_eligible = 1 means this receipt can be refunded.")
    recent_recs = ctx.get_recent_receipts(ctx.DB, limit=15)
    if recent_recs:
        rec_df = pd.DataFrame(recent_recs)
        rec_df["refund_eligible"] = rec_df["refund_eligible"].map(
            {1: "✅ Yes", 0: "❌ No"})
        st.dataframe(rec_df, use_container_width=True, height=320, hide_index=True)

    st.divider()

    # ── FAILED REFUNDS — real data, not claims ────────────
    st.subheader("⚠️ Failed Refunds — Needing Manual Retry")
    st.caption("These are real rows from the refunds table where "
               "status='failed'. Each one = a customer waiting for money. "
               "Action required within 24h.")
    failed_list = ctx.get_failed_refunds(ctx.DB)
    if failed_list:
        fd = pd.DataFrame(failed_list)
        st.dataframe(fd, use_container_width=True, height=260, hide_index=True)
        st.error(f"🔴 {len(failed_list)} refunds need manual retry with gateway.")
    else:
        st.success("✅ No failed refunds — all processed cleanly.")

    # ── RECONCILIATION ────────────────────────────────────
    st.divider()
    st.subheader("🔁 Gateway Reconciliation")
    st.caption("Daily comparison: our DB totals vs what the gateway reports. "
               "Formula: matched=1 if |our_total - gateway_total| < ₹0.01. "
               "Source: payment_reconciliation table.")
    recon_df = ctx.q("""
        SELECT recon_date, our_count, gateway_count,
               our_total_inr, gateway_total_inr,
               CASE WHEN matched=1 THEN '✅ MATCHED' ELSE '⚠️ DISCREPANCY' END AS status,
               discrepancy_inr, notes
        FROM payment_reconciliation ORDER BY recon_date DESC
    """)
    st.dataframe(recon_df, use_container_width=True, height=280, hide_index=True)
    match_rate = rm8.get("reconciliation_match_rate", 0)
    if match_rate == 100:
        st.success(f"✅ {match_rate}% reconciliation match rate — all days verified.")
    else:
        st.warning(f"⚠️ {match_rate}% match rate — investigate unmatched days immediately.")


    # ═══════════════════════════════════════════════════════
    # TAB 4 — ARPU + COHORT REVENUE (Task 9 centrepiece)
    # ═══════════════════════════════════════════════════════
