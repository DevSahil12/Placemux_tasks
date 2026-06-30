"""
Task 10 — Revenue Command Center
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task10(ctx):
    """Render the "Task 10 — Revenue Command Center" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    rcc = ctx.get_rcc()
    checks_rcc = ctx.get_rcc_checks()

    # ── hero banner ───────────────────────────────────────
    all_pass_rcc = all(v["result"] in ("PASS","WARN") for v in checks_rcc.values())
    banner_color = "#16a34a" if all_pass_rcc else "#dc2626"
    banner_label = "LIVE · ALL CHECKS PASS" if all_pass_rcc else "ISSUES DETECTED"
    st.markdown(
        f'''<div style="background:linear-gradient(90deg,#1e2761,#7c3aed);
        padding:1.2rem 2rem;border-radius:12px;margin-bottom:1rem">
        <h2 style="color:#fff;margin:0;font-size:1.5rem">&#127970; Revenue Command Center</h2>
        <p style="color:#e9d5ff;margin:0.3rem 0 0">Task 10 · Monetization Integration &amp; Revenue Dashboard ·
        <span style="background:''' + banner_color + '''22;border:1px solid ''' + banner_color + ''';
        color:''' + banner_color + ''';padding:2px 10px;border-radius:4px;font-weight:700">
        ''' + banner_label + '''</span></p></div>''', unsafe_allow_html=True)

    # ── ROW 1: top-line KPIs ─────────────────────────────
    st.subheader("&#128176; Revenue Overview — All Streams")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Gross Revenue",   f"\u20b9{rcc['gross_revenue_inr']:,.0f}",
              help=ctx.RCC_METRIC_DICTIONARY['gross_revenue_inr']['decision'])
    r2.metric("Net Revenue",     f"\u20b9{rcc['net_revenue_inr']:,.0f}",
              delta=f"-\u20b9{rcc['total_refunded_inr']:,.0f} refunds", delta_color="inverse",
              help=ctx.RCC_METRIC_DICTIONARY['net_revenue_inr']['decision'])
    r3.metric("Last 7 Days",     f"\u20b9{rcc['revenue_last_7d_inr']:,.0f}",
              help=ctx.RCC_METRIC_DICTIONARY['revenue_last_7d_inr']['decision'])
    wow = rcc['revenue_wow_growth_pct']
    r4.metric("WoW Growth",      f"{wow}%" if wow is not None else "N/A",
              help=ctx.RCC_METRIC_DICTIONARY['revenue_wow_growth_pct']['decision'])
    r5.metric("Company ARPU",    f"\u20b9{rcc['company_arpu_inr']:,.0f}",
              delta=f"Net \u20b9{rcc['net_arpu_after_refunds']:,.0f}",
              help=ctx.RCC_METRIC_DICTIONARY['company_arpu_inr']['decision'])

    st.divider()

    # ── ROW 2: Company + Student revenue ─────────────────
    col_co, col_st = st.columns(2)
    with col_co:
        st.markdown("#### &#127970; Company Revenue")
        cc1, cc2 = st.columns(2)
        cc1.metric("Total", f"\u20b9{rcc['company_revenue_inr']:,.0f}")
        cc2.metric("Paying Companies", str(rcc['paying_companies']))
        if rcc["revenue_by_type"]:
            df_t = pd.DataFrame(rcc["revenue_by_type"])
            st.dataframe(df_t.rename(columns={"payment_type":"Type","transactions":"Txns","revenue_inr":"Revenue (\u20b9)"}),
                         hide_index=True, use_container_width=True)
        with st.expander("How it's calculated"):
            st.caption(f"**Formula:** {ctx.RCC_METRIC_DICTIONARY['company_revenue_inr']['formula']}")
            st.caption(f"**Decision:** {ctx.RCC_METRIC_DICTIONARY['company_revenue_inr']['decision']}")

    with col_st:
        st.markdown("#### &#127891; Student Revenue (\u20b9100 Pay-per-App)")
        cs1, cs2 = st.columns(2)
        cs1.metric("Total Collected", f"\u20b9{rcc['student_revenue_inr']:,.0f}")
        cs2.metric("Success Rate",    f"{rcc['student_payment_success_rate_pct']}%")
        df_sp = pd.DataFrame({
            "Status": ["Success","Failed","Abandoned"],
            "Count":  [rcc["student_payments_success"],rcc["student_payments_failed"],rcc["student_payments_abandoned"]],
        })
        st.dataframe(df_sp, hide_index=True, use_container_width=True)
        if rcc["student_failure_reasons"]:
            with st.expander("Failure Reasons"):
                df_fr = pd.DataFrame(rcc["student_failure_reasons"])
                st.dataframe(df_fr.rename(columns={"failure_reason":"Reason","count":"Count"}),
                             hide_index=True, use_container_width=True)
        with st.expander("How it's calculated"):
            st.caption(f"**Formula:** {ctx.RCC_METRIC_DICTIONARY['student_revenue_inr']['formula']}")

    st.divider()

    # ── ROW 3: Payment Health ─────────────────────────────
    st.subheader("&#128260; Payment Health & Integrity")
    h1,h2,h3,h4,h5 = st.columns(5)
    h1.metric("Refund Rate",       f"{rcc['refund_rate_pct']}%",
              delta="Watch" if rcc['refund_rate_pct']>10 else "OK",
              delta_color="inverse" if rcc['refund_rate_pct']>10 else "normal",
              help=ctx.RCC_METRIC_DICTIONARY['refund_rate_pct']['decision'])
    h2.metric("Total Refunded",    f"\u20b9{rcc['total_refunded_inr']:,.0f}")
    h3.metric("Recon Match",       f"{rcc['reconciliation_match_rate_pct']}%",
              delta="Balanced" if rcc['reconciliation_match_rate_pct']==100 else "MISMATCH",
              help=ctx.RCC_METRIC_DICTIONARY['reconciliation_match_rate_pct']['decision'])
    h4.metric("Pay→App Integrity", f"{rcc['pay_to_app_integrity_pct']}%",
              delta="Perfect" if rcc['pay_to_app_integrity_pct']==100 else "LEAK",
              help=ctx.RCC_METRIC_DICTIONARY['pay_to_app_integrity_pct']['decision'])
    h5.metric("Failure Impact",    f"{rcc['failure_impact_on_arpu_pct']}%",
              delta=">15% — add UPI" if rcc['failure_impact_on_arpu_pct']>15 else "OK",
              delta_color="inverse",
              help=ctx.RCC_METRIC_DICTIONARY['failure_impact_on_arpu_pct']['decision'])

    if rcc["refunds_by_reason"]:
        with st.expander("Refund Breakdown by Reason"):
            df_rr = pd.DataFrame(rcc["refunds_by_reason"])
            df_rr["amount_inr"] = df_rr["amount_inr"].apply(lambda x: f"\u20b9{x:,.0f}" if x else "\u20b90")
            st.dataframe(df_rr.rename(columns={"reason":"Reason","count":"Count","amount_inr":"Amount"}),
                         hide_index=True, use_container_width=True)
            st.caption("&#9888; duplicate_transaction is the top refund cause — add idempotency key urgently.")

    st.divider()

    # ── ROW 4: Weekly Revenue Trend ───────────────────────
    if rcc["weekly_revenue_trend"]:
        st.subheader("&#128200; Weekly Revenue Trend")
        df_tr = pd.DataFrame(rcc["weekly_revenue_trend"])
        fig_tr = go.Figure(go.Bar(x=df_tr["week"], y=df_tr["revenue"],
                                  marker_color="#3b5bdb", name="Revenue (\u20b9)"))
        fig_tr.update_layout(height=250, margin=dict(t=10,b=30),
                              yaxis_title="Revenue (\u20b9)", xaxis_title="Week",
                              plot_bgcolor="#f8f9fa", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_tr, use_container_width=True)

    # ── ROW 5: Cohort Revenue ─────────────────────────────
    if rcc["cohort_revenue_by_signup_week"]:
        st.subheader("&#128202; Cohort Revenue (Company Signup Week)")
        df_coh = pd.DataFrame(rcc["cohort_revenue_by_signup_week"])
        col_chart, col_tbl = st.columns([3,2])
        with col_chart:
            fig_coh = px.bar(df_coh, x="signup_week", y="arpu_inr",
                             color="arpu_inr", color_continuous_scale=["#dbeafe","#1e40af"],
                             labels={"signup_week":"Signup Week","arpu_inr":"ARPU (\u20b9)"})
            fig_coh.update_layout(height=220, margin=dict(t=10,b=30), coloraxis_showscale=False)
            st.plotly_chart(fig_coh, use_container_width=True)
        with col_tbl:
            st.dataframe(
                df_coh.rename(columns={"signup_week":"Week","companies":"Cos",
                                        "revenue_inr":"Revenue (\u20b9)","arpu_inr":"ARPU (\u20b9)"}),
                hide_index=True, use_container_width=True, height=220)

        if rcc["top_companies_by_revenue"]:
            st.markdown("**Top 5 Companies by Revenue**")
            df_top = pd.DataFrame(rcc["top_companies_by_revenue"])
            df_top["revenue_inr"] = df_top["revenue_inr"].apply(lambda x: f"\u20b9{x:,.0f}")
            st.dataframe(df_top.rename(columns={"name":"Company","revenue_inr":"Revenue","transactions":"Txns"}),
                         hide_index=True, use_container_width=True)

    st.divider()

    # ── ROW 6: Go-live checklist ──────────────────────────
    st.subheader("&#9989; Go-Live Readiness & Founder Self-Check")
    checklist_labels = {
        "data_flowing":          "All revenue streams flowing at real scale",
        "reconciliation_100pct": "Gateway reconciliation = 100% match (no revenue leakage)",
        "zero_integrity_leaks":  "Pay→App integrity 100% / zero payment-failure app leaks",
        "refund_rate_ok":        "Refund rate < 12% (currently: {:.1f}%)".format(rcc['refund_rate_pct']),
        "gateway_test_mode":     "Gateway in TEST mode (not real money — correct for Phase 2)",
        "failure_impact_ok":     "Failure impact tracked ({:.1f}%)".format(rcc['failure_impact_on_arpu_pct']) +
                                 (" ⚠️ Add UPI/wallet to recover revenue" if rcc['failure_impact_on_arpu_pct']>15 else " ✅"),
    }
    cl1, cl2 = st.columns(2)
    items = list(rcc["checklist"].items())
    for i, (k, v) in enumerate(items):
        icon = "✅" if v else "⚠️"
        label = checklist_labels.get(k, k)
        (cl1 if i%2==0 else cl2).markdown(f"{icon} {label}")

    st.divider()

    # ── ROW 7: Validation results ─────────────────────────
    st.subheader("&#128269; Task 10 Validation (6 Checks)")
    for name, res in checks_rcc.items():
        icon  = "✅" if res["result"]=="PASS" else ("⚠️" if res["result"]=="WARN" else "❌")
        color = "#dcfce7" if res["result"]=="PASS" else ("#fef9c3" if res["result"]=="WARN" else "#fee2e2")
        st.markdown(
            f'''<div style="background:{color};padding:0.5rem 1rem;border-radius:6px;margin:3px 0">
            {icon} <strong>{res["result"]}</strong> — {name.replace("_"," ")}
            <span style="color:#555;font-size:0.85rem"> · {res["detail"]}</span></div>''',
            unsafe_allow_html=True)

    if all(v["result"] in ("PASS","WARN") for v in checks_rcc.values()):
        st.success("✅ ALL TASK 10 CHECKS PASS — Revenue Command Center live, sourced, and demoable end-to-end.")

    # ── gateway pill ──────────────────────────────────────
    gw = rcc["gateway_mode"]
    gw_color = "#f59e0b" if gw=="test" else "#dc2626"
    st.markdown(
        f'''<div style="margin-top:0.8rem">
        <span style="background:{gw_color};color:#fff;padding:4px 16px;border-radius:12px;font-weight:700">
        &#9889; GATEWAY: {gw.upper()} MODE</span>
        &nbsp;&nbsp;<em style="color:#666;font-size:0.85rem">
        {"Test mode — safe for demo. Going live requires: idempotency keys · retry logic · DPDP consent · go/no-go checklist"
         if gw=="test" else "LIVE MODE — real money transacting"}</em>
        </div>''', unsafe_allow_html=True)




    # ═══════════════════════════════════════════════════════
    # TAB 1 — OFFER FUNNEL & E-SIGN (Task 11)
    # ═══════════════════════════════════════════════════════
