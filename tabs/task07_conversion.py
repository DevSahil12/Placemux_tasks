"""
Task 7 — Conversion Baseline
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task07(ctx):
    """Render the "Task 7 — Conversion Baseline" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    cm = ctx.get_conversion()

    st.subheader("🔁 Conversion Baseline — Pay-per-Application (₹100)")
    st.caption("A student pays ₹100 to apply to a job. This tab tracks the "
               "full funnel: viewed → pay initiated → pay success/failed → "
               "application created. Gateway mode: **TEST** (no real money yet).")

    # ── headline metrics ────────────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    e2e = cm["end_to_end_conversion_rate"]
    e2e_color = "#22c55e" if e2e >= 20 else ("#f59e0b" if e2e >= 10 else "#ef4444")
    c1.metric("End-to-End Conversion", f"{e2e}%",
              help="% of views that ended in a paid application. "
                   "Formula: COUNT(application_created)/COUNT(job_viewed)×100")
    c2.metric("Payment Success Rate", f"{cm['payment_success_rate']}%",
              help="% of payment attempts confirmed by gateway. "
                   "Formula: COUNT(pay_per_app_success)/COUNT(pay_per_app_initiated)×100")
    c3.metric("Pay→App Integrity", f"{cm['payment_to_application_rate']}%",
              help="% of successful payments that created an application. "
                   "Must be 100%. Any < 100% = student paid but got no app = bug.")
    c4.metric("Revenue (₹100 fees)", f"₹{cm['revenue_from_conversions_inr']:,.0f}",
              help="Total ₹100 fees collected. "
                   "Formula: SUM(amount_inr) WHERE status='success'")

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("View→Pay Rate",    f"{cm['view_to_pay_initiated_rate']}%",
              help="Formula: COUNT(pay_per_app_initiated)/COUNT(job_viewed)×100")
    c6.metric("Abandonment Rate", f"{cm['abandonment_rate']}%",
              help="Formula: COUNT(application_abandoned)/COUNT(pay_per_app_initiated)×100")
    c7.metric("Avg Convert Time", f"{cm['avg_time_to_convert_seconds']}s",
              help="Avg seconds from pay_initiated to application_created")
    c8.metric("Gateway Mode",
              "✅ TEST" if "test" in (cm["gateway_mode"] or []) else "⚠️ LIVE",
              help="Must be 'test' until go-live checklist signed off")

    st.divider()

    # ── conversion funnel chart ─────────────────────────────────
    col_f, col_b = st.columns([2, 1])
    with col_f:
        f = cm["_funnel"]
        funnel_df = pd.DataFrame({
            "stage": list(f.keys()),
            "count": list(f.values())
        })
        fig_conv = go.Figure(go.Funnel(
            y=funnel_df["stage"], x=funnel_df["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#1e2761","#3b5bdb","#22c55e",
                               "#a5b4fc","#ef4444","#f59e0b"])
        ))
        fig_conv.update_layout(
            title="Student Pay-per-Application Funnel (₹100 flow)",
            height=380, margin=dict(t=40,b=10))
        st.plotly_chart(fig_conv, use_container_width=True)

    with col_b:
        st.markdown("**Failure Breakdown**")
        if cm["failure_rate_by_reason"]:
            fail_df = pd.DataFrame([
                {"Reason": k, "% of Failures": v}
                for k, v in cm["failure_rate_by_reason"].items()
            ])
            fig_fail = px.pie(fail_df, names="Reason", values="% of Failures",
                              color_discrete_sequence=px.colors.sequential.RdBu)
            fig_fail.update_layout(height=280, margin=dict(t=10,b=10))
            st.plotly_chart(fig_fail, use_container_width=True)

    st.divider()

    # ── METRIC DICTIONARY — addresses "no explanation of calculations" ──
    st.subheader("📖 How Each Metric Is Calculated")
    st.caption("Every metric shows its exact formula, source table, and the "
               "decision it informs — so the founder can verify any number "
               "independently.")
    for name, defn in ctx.CONVERSION_METRIC_DICTIONARY.items():
        val = cm.get(name)
        val_str = str(val) if not isinstance(val, float) else f"{val:.1f}"
        if name == "failure_rate_by_reason":
            val_str = str(cm.get(name, {}))
        with st.expander(f"**{name}** = {val_str}", expanded=False):
            st.markdown(f"**Definition:** {defn['definition']}")
            st.code(defn['formula'], language="sql")
            st.markdown(f"**Source table:** `{defn['source']}`")
            st.markdown(f"**Decision:** _{defn['decision']}_")
            st.markdown(f"**Expected range:** {defn['expected_range']}")

    st.divider()

    # ── ERROR HANDLING — real examples, not claims ──────────────
    st.subheader("⚠️ Error Handling — Real Data Examples")
    st.caption("These are actual rows from the database proving that "
               "failure handling works correctly, not just claimed to work.")

    st.markdown("**What happens when a payment FAILS?**")
    st.info("The student loses **no money** (payment never completed) and "
            "their **application is never created** (application_id = NULL). "
            "They can retry without re-viewing the job. "
            "The `conversion_events` log records exactly why it failed.")

    failures = ctx.get_failure_examples(ctx.DB, limit=5)
    if failures:
        fail_df = pd.DataFrame(failures)
        fail_df["application_created?"] = fail_df["application_id"].apply(
            lambda x: "✅ NO (correct)" if x is None else f"❌ YES — BUG (id={x})"
        )
        st.dataframe(
            fail_df[["sp_id","student","job","failure_reason",
                      "initiated_at","application_created?"]],
            use_container_width=True, hide_index=True
        )
    integrity = ctx.q("SELECT COUNT(*) n FROM student_payments WHERE status='failed' AND application_id IS NOT NULL").iloc[0,0]
    if integrity == 0:
        st.success("✅ CONFIRMED: 0 failed payments accidentally created an application.")

    st.markdown("**What happens when a student ABANDONS payment?**")
    st.info("Student clicked 'Apply & Pay' but left before completing. "
            "Same outcome as failure: no application created, no money taken. "
            "The `application_abandoned` event fires after a 30-minute timeout.")
    abandoned = ctx.get_abandonment_examples(ctx.DB, limit=5)
    if abandoned:
        ab_df = pd.DataFrame(abandoned)
        ab_df["application_created?"] = ab_df["application_id"].apply(
            lambda x: "✅ NO (correct)" if x is None else f"❌ YES — BUG"
        )
        st.dataframe(
            ab_df[["sp_id","student","job","initiated_at","application_created?"]],
            use_container_width=True, hide_index=True
        )

    st.divider()

    # ── Recent conversion events (live feed) ────────────────────
    st.subheader("Recent Conversion Events (live)")
    recent_ce = ctx.q("""
        SELECT ce.emitted_at, s.student_name, j.job_title,
               ce.event_name, ce.amount_inr, ce.failure_reason,
               ce.gateway_mode,
               CASE WHEN ce.application_id IS NOT NULL
                    THEN 'YES' ELSE 'NO' END AS app_created
        FROM conversion_events ce
        JOIN students s ON ce.student_id = s.student_id
        JOIN jobs j ON ce.job_id = j.job_id
        ORDER BY ce.emitted_at DESC LIMIT 30
    """)
    st.dataframe(recent_ce, use_container_width=True, height=360)


    # ═══════════════════════════════════════════════════════
    # TAB 3 — REFUND/FAILURE ANALYTICS (Task 8 centrepiece)
    # ═══════════════════════════════════════════════════════
