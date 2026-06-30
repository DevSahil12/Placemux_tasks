"""
Task 6 — Revenue Metrics
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task06(ctx):
    """Render the "Task 6 — Revenue Metrics" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    rev = ctx.get_revenue()

    st.subheader("💰 Revenue Metrics — Payments Design & Gateway Setup")
    st.caption("All numbers sourced from payment_events (immutable log) + payments (entity table). "
               "Gateway mode: TEST — no real money collected yet.")

    # ── gateway status banner ─────────────────────────────
    gw_modes = rev["gateway_mode"]
    if "live" not in gw_modes:
        st.info("🧪 Gateway Mode: **TEST** — All payments are synthetic. "
                "0 live-mode rows confirmed in DB. See go-live checklist below.")
    else:
        st.error("🔴 LIVE mode detected — confirm this was intentional before proceeding.")

    # ── hero KPIs ─────────────────────────────────────────
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("💰 Total Revenue (INR)",
              f"₹{rev['total_revenue_inr']:,.0f}",
              help=ctx.REVENUE_METRIC_DICTIONARY["total_revenue_inr"]["decision"])
    c2.metric("📅 Revenue (Last 7d)",
              f"₹{rev['revenue_last_7d']:,.0f}",
              help=ctx.REVENUE_METRIC_DICTIONARY["revenue_last_7d"]["decision"])
    c3.metric("✅ Payment Success Rate",
              f"{rev['payment_success_rate']}%",
              help=ctx.REVENUE_METRIC_DICTIONARY["payment_success_rate"]["decision"])
    c4.metric("🏢 Paying Companies",
              rev["paying_companies"],
              help=ctx.REVENUE_METRIC_DICTIONARY["paying_companies"]["decision"])
    c5.metric("💎 ARPC (INR)",
              f"₹{rev['arpc_inr']:,.0f}",
              help=ctx.REVENUE_METRIC_DICTIONARY["arpc_inr"]["decision"])

    c6,c7,c8 = st.columns(3)
    c6.metric("❌ Failure Rate",
              f"{rev['payment_failure_rate']}%",
              help=ctx.REVENUE_METRIC_DICTIONARY["payment_failure_rate"]["decision"])
    c7.metric("🔄 Refund Rate",
              f"{rev['refund_rate']}%",
              help=ctx.REVENUE_METRIC_DICTIONARY["refund_rate"]["decision"])
    c8.metric("🎯 Conversion to Paid",
              f"{rev['conversion_to_paid_rate']}%",
              help=ctx.REVENUE_METRIC_DICTIONARY["conversion_to_paid_rate"]["decision"])

    st.divider()
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        # revenue by type pie
        rev_type = rev["revenue_by_type"]
        if rev_type:
            fig_rtype = px.pie(
                names=list(rev_type.keys()),
                values=list(rev_type.values()),
                title="Revenue by Payment Type",
                color_discrete_sequence=["#1e2761","#3b5bdb","#22c55e"]
            )
            fig_rtype.update_layout(height=300, margin=dict(t=40,b=10))
            st.plotly_chart(fig_rtype, use_container_width=True)

    with col_r2:
        # payment funnel
        pay_funnel = pd.DataFrame({
            "stage":  ["Initiated","Success","Failed","Refunded"],
            "count": [
                ctx.q("SELECT COUNT(*) n FROM payments").iloc[0,0],
                ctx.q("SELECT COUNT(*) n FROM payments WHERE status='success'").iloc[0,0],
                ctx.q("SELECT COUNT(*) n FROM payments WHERE status='failed'").iloc[0,0],
                ctx.q("SELECT COUNT(*) n FROM payments WHERE status='refunded'").iloc[0,0],
            ]
        })
        fig_pfunnel = go.Figure(go.Funnel(
            y=pay_funnel["stage"], x=pay_funnel["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#1e2761","#22c55e","#ef4444","#f59e0b"])
        ))
        fig_pfunnel.update_layout(title="Payment Funnel", height=300,
                                   margin=dict(t=40,b=10))
        st.plotly_chart(fig_pfunnel, use_container_width=True)

    # failure reason breakdown
    st.subheader("❌ Failure Reason Breakdown")
    st.caption("Each reason maps to a different action — don't treat all failures the same.")
    fail_reasons = rev.get("failure_reason_breakdown", {})
    if fail_reasons:
        fr_df = pd.DataFrame({"reason": list(fail_reasons.keys()),
                              "count":  list(fail_reasons.values())})
        fr_df["action"] = fr_df["reason"].map({
            "insufficient_funds": "Pricing may be high for segment — consider EMI option",
            "card_declined":      "Wrong payment method offered — add UPI/netbanking",
            "gateway_timeout":    "Infrastructure issue — check gateway SLA",
            "invalid_vpa":        "UX validation missing for VPA field — fix frontend",
            "bank_server_error":  "Intermittent — retry automatically, alert if > 5% of failures",
        })
        fig_fail = px.bar(fr_df, x="count", y="reason", orientation="h",
                          color="count", color_continuous_scale=["#fef9c3","#ef4444"],
                          title="Failures by Reason (each has a different fix)")
        fig_fail.update_layout(height=300, margin=dict(t=40,b=10),
                               coloraxis_showscale=False,
                               yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_fail, use_container_width=True)
        st.dataframe(fr_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🔗 Gateway Reconciliation")
    st.caption("How we know our records match exactly what the gateway collected.")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        recon = ctx.q("""
            SELECT gateway_ref, amount_inr,
                   initiated_at, resolved_at, status, failure_reason
            FROM payments
            ORDER BY initiated_at DESC LIMIT 20
        """)
        st.dataframe(recon, use_container_width=True, height=280)
    with col_g2:
        st.markdown("**Reconciliation Logic**")
        st.markdown("""
    Each payment fires **two events** in `payment_events`:

    1. `payment_initiated` — when PlaceMux sends the charge
    2. `payment_success` / `payment_failed` — when gateway responds

    `gateway_ref` is the key that links our row to the gateway's own settlement report. On Day 1 of real money:

    ```sql
    -- Compare our records to gateway settlement file
    SELECT pe.gateway_ref, pe.amount_inr AS our_amount,
       gw.amount AS gateway_amount,
       pe.amount_inr - gw.amount AS discrepancy
    FROM payment_events pe
    JOIN gateway_settlement gw
      ON pe.gateway_ref = gw.reference_id
    WHERE pe.event_name = 'payment_success'
      AND ABS(pe.amount_inr - gw.amount) > 0;
    ```
    Any row returned = discrepancy to investigate before EOD.
    """)

    st.divider()
    st.subheader("🚀 Go-Live Checklist")
    st.caption("What's left before switching from test mode to real money.")
    checklist = [
        ("Replace TEST_ gateway_ref prefix with real credentials (Razorpay/Stripe)", False),
        ("Set gateway_mode='live' only after founder explicit sign-off", False),
        ("Enable webhook endpoint — gateway posts callbacks to payment_events", False),
        ("Run Day 1 reconciliation (compare our DB vs gateway settlement file)", False),
        ("Wire failure_reason alerts to ops team (Slack/email)", False),
        ("Confirm payment failure does NOT affect application.status", True),
        ("Confirm 0 unreconciled stuck payments at EOD", True),
    ]
    for item, done in checklist:
        icon = "✅" if done else "⬜"
        st.markdown(f"{icon} {item}")

    st.divider()
    st.subheader("📖 Revenue Metric Dictionary")
    rows = []
    for name, defn in ctx.REVENUE_METRIC_DICTIONARY.items():
        rows.append({
            "Metric":   name,
            "Value":    str(rev.get(name, "—")),
            "Source":   defn["source"],
            "Decision": defn["decision"][:90],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True, height=480)


    # ═══════════════════════════════════════════════════════
    # TAB 2 — CONVERSION BASELINE (Task 7 centrepiece)
    # ═══════════════════════════════════════════════════════
