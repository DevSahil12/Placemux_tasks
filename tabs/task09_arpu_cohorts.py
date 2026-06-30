"""
Task 9 — ARPU & Cohort Revenue
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task09(ctx):
    """Render the "Task 9 — ARPU & Cohort Revenue" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    am = ctx.get_arpu()

    st.subheader("📈 ARPU + Cohort Revenue — Failure Handling & Resilience")
    st.caption("Deep revenue view: ARPU by payer type, cohort analysis by signup week "
               "and industry, failure impact on ARPU, and net revenue after refunds.")

    # ── headline ARPU cards ─────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("ARPU (Company)", f"₹{am['arpu_company_inr']:,.0f}",
              help="Formula: SUM(amount_inr)/COUNT(DISTINCT company_id) "
                   "FROM payments WHERE status='success'")
    c2.metric("ARPU (Student)", f"₹{am['arpu_student_inr']:,.0f}",
              help="Formula: SUM(amount_inr)/COUNT(DISTINCT student_id) "
                   "FROM student_payments WHERE status='success'")
    c3.metric("ARPU (Blended)", f"₹{am['arpu_blended_inr']:,.0f}",
              help="Formula: total_revenue / (distinct_companies + distinct_students)")
    c4.metric("Net ARPU (after refunds)", f"₹{am['net_arpu_after_refunds']:,.0f}",
              help="Formula: (company revenue - refunds processed) / paying companies")

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("Revenue per Job Posted", f"₹{am['revenue_per_job_posted']:,.0f}",
              help="Formula: SUM(amount_inr)/COUNT(DISTINCT job_id) WHERE job_id IS NOT NULL")
    fi = am["failure_impact_on_arpu"]
    fi_color = "normal" if fi <= 15 else "inverse"
    c6.metric("Failure Impact on ARPU", f"{fi}%",
              delta="⚠️ Above 15% threshold — add payment methods" if fi > 15 else "✅ Within range",
              delta_color=fi_color,
              help="Formula: SUM(failed amount) / SUM(all attempted amount) × 100")
    c7.metric("Repeat Payment Rate", f"{am['cohort_repeat_payment_rate']}%",
              help="Formula: COUNT(companies with >1 payment) / COUNT(paying companies) × 100")
    gross_arpu = am["arpu_company_inr"]
    net_arpu   = am["net_arpu_after_refunds"]
    c8.metric("Refund Drag on ARPU",
              f"{round((gross_arpu-net_arpu)/gross_arpu*100,1)}%",
              help="(gross_arpu - net_arpu) / gross_arpu × 100")

    st.divider()

    # ── cohort revenue by signup week ───────────────────
    cohort_data = am.get("cohort_revenue_by_signup_week", [])
    if cohort_data:
        cohort_df = pd.DataFrame(cohort_data)
        col_ch1, col_ch2 = st.columns(2)
        with col_ch1:
            fig_ch = px.bar(cohort_df, x="week", y="revenue_inr",
                            title="Revenue by Company Signup Week (Cohort Analysis)",
                            color="arpu_inr", color_continuous_scale="Blues",
                            labels={"revenue_inr":"Revenue (₹)","week":"Signup Week",
                                    "arpu_inr":"ARPU (₹)"})
            fig_ch.update_layout(height=320, margin=dict(t=40,b=10))
            st.plotly_chart(fig_ch, use_container_width=True)
        with col_ch2:
            fig_arpu = px.line(cohort_df, x="week", y="arpu_inr",
                               title="ARPU Trend by Signup Cohort",
                               markers=True,
                               color_discrete_sequence=["#1e2761"])
            fig_arpu.add_hline(y=cohort_df["arpu_inr"].mean(),
                               line_dash="dash", line_color="#f59e0b",
                               annotation_text=f"Avg ₹{cohort_df['arpu_inr'].mean():,.0f}")
            fig_arpu.update_layout(height=320, margin=dict(t=40,b=10))
            st.plotly_chart(fig_arpu, use_container_width=True)
        st.caption("**How to read this:** Each bar = one signup-week cohort. "
                   "Bar height = total revenue from that cohort. "
                   "Colour = ARPU for that cohort. "
                   "Source: `payments JOIN companies ON company_id WHERE status='success'`")

    st.divider()

    # ── revenue by industry cohort ──────────────────────
    industry_data = am.get("revenue_by_industry_cohort", [])
    if industry_data:
        ind_df = pd.DataFrame(industry_data)
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            fig_ind = px.bar(ind_df.sort_values("revenue_inr"),
                             x="revenue_inr", y="industry", orientation="h",
                             color="arpu_inr", color_continuous_scale="Teal",
                             title="Revenue by Industry Cohort",
                             labels={"revenue_inr":"Revenue (₹)",
                                     "industry":"Industry","arpu_inr":"ARPU (₹)"})
            fig_ind.update_layout(height=320, margin=dict(t=40,b=10),
                                  coloraxis_showscale=False)
            st.plotly_chart(fig_ind, use_container_width=True)
        with col_i2:
            fig_arpu_ind = px.bar(ind_df.sort_values("arpu_inr", ascending=False),
                                  x="industry", y="arpu_inr",
                                  title="ARPU by Industry",
                                  color="arpu_inr", color_continuous_scale="Greens",
                                  labels={"arpu_inr":"ARPU (₹)"})
            fig_arpu_ind.update_layout(height=320, margin=dict(t=40,b=10),
                                       coloraxis_showscale=False)
            st.plotly_chart(fig_arpu_ind, use_container_width=True)

    st.divider()

    # ── daily revenue trend ─────────────────────────────
    daily_data = am.get("_daily_revenue", [])
    if daily_data:
        daily_df = pd.DataFrame(daily_data)
        fig_daily = px.bar(daily_df, x="date", y="revenue_inr", color="source",
                           title="Daily Revenue (Company + Student)",
                           color_discrete_map={"company":"#1e2761","student":"#3b5bdb"},
                           labels={"revenue_inr":"Revenue (₹)","date":"Date"})
        fig_daily.update_layout(height=300, margin=dict(t=40,b=10))
        st.plotly_chart(fig_daily, use_container_width=True)

    st.divider()

    # ── cohort by company age band ──────────────────────
    age_data = am.get("_cohort_by_age", [])
    if age_data:
        age_df = pd.DataFrame(age_data)
        st.subheader("Revenue by Company Age Band")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            fig_age = px.pie(age_df, names="age_band", values="revenue_inr",
                             title="Revenue Share by Company Age",
                             color_discrete_sequence=["#1e2761","#3b5bdb","#a5b4fc"])
            fig_age.update_layout(height=280, margin=dict(t=40,b=10))
            st.plotly_chart(fig_age, use_container_width=True)
        with col_a2:
            st.dataframe(age_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── failure impact section ──────────────────────────
    st.subheader("⚠️ Failure Impact on ARPU — Actionable Finding")
    fi_val = am["failure_impact_on_arpu"]
    if fi_val > 15:
        st.error(f"**{fi_val}%** of attempted revenue is being lost to payment failures "
                 f"(threshold: 15%). This is the single biggest suppressant of ARPU "
                 f"right now — more impactful than adding new companies.")
        st.markdown("""
        **What this means:**
        - For every ₹100 a company tries to pay, ₹18.30 is being lost to failures
        - Adding more payment methods (UPI, wallet) would recover this without any new acquisition
        - **Formula:** `SUM(failed amount) / SUM(all attempted amount) × 100`
        - **Source:** `payments + student_payments`
        """)
    else:
        st.success(f"**{fi_val}%** — within acceptable range (< 15%). "
                   "Payment friction is not the primary ARPU limiter.")

    st.divider()

    # ── metric dictionary ───────────────────────────────
    st.subheader("📖 How Each Metric Is Calculated")
    scalar_metrics = {k: v for k, v in am.items()
                      if not k.startswith("_") and not isinstance(v, list)}
    for name, val in scalar_metrics.items():
        defn = ctx.ARPU_METRIC_DICTIONARY.get(name, {})
        val_str = f"₹{val:,.2f}" if isinstance(val, float) else str(val)
        with st.expander(f"**{name}** = {val_str}", expanded=False):
            st.markdown(f"**Definition:** {defn.get('definition','—')}")
            st.code(defn.get("formula","—"), language="sql")
            st.markdown(f"**Source:** `{defn.get('source','—')}`")
            st.markdown(f"**Decision:** _{defn.get('decision','—')}_")
            st.markdown(f"**Expected range:** {defn.get('expected_range','—')}")

    # ── cohort data table ───────────────────────────────
    st.subheader("Full Cohort Revenue Table")
    if cohort_data:
        st.dataframe(pd.DataFrame(cohort_data), use_container_width=True, hide_index=True)


    # ═══════════════════════════════════════════════════════
    # TAB 5 — OVERVIEW (Task 1 metrics)
    # ═══════════════════════════════════════════════════════
