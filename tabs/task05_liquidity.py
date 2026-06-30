"""
Task 5 — Liquidity Dashboard
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task05(ctx):
    """Render the "Task 5 — Liquidity Dashboard" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    metrics = ctx.get_metrics()
    li      = metrics["liquidity_index"]
    label, li_color, action = ctx.health_status(li)

    # ── hero: Liquidity Index ─────────────────────────────
    st.markdown(
        f'<div style="background:{li_color}22;border-left:6px solid {li_color};'
        f'padding:1rem 1.5rem;border-radius:8px;margin-bottom:1rem">'
        f'<span style="font-size:2.2rem;font-weight:700;color:{li_color}">'
        f'{li}/100</span>'
        f'<span style="font-size:1.1rem;font-weight:600;color:{li_color};margin-left:1rem">'
        f'[{label}]</span><br>'
        f'<span style="font-size:0.95rem;color:#444">{action}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    def fmt(v, suffix=""):
        if v is None: return "N/A"
        if isinstance(v, float): return f"{v:.1f}{suffix}"
        return f"{v}{suffix}"

    # ── gauge ────────────────────────────────────────────
    col_g, col_components = st.columns([1, 2])
    with col_g:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=li,
            title={"text": "Liquidity Index", "font": {"size": 17}},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": li_color},
                "steps": [
                    {"range": [0, 50],  "color": "#fee2e2"},
                    {"range": [50, 70], "color": "#fef9c3"},
                    {"range": [70, 100],"color": "#dcfce7"},
                ],
                "threshold": {"line": {"color": "#1e2761","width": 3},"value": li}
            }
        ))
        fig_gauge.update_layout(height=260, margin=dict(t=30,b=10,l=20,r=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col_components:
        st.markdown("**Component Breakdown**")
        components = {
            "Fill Proxy (apply→shortlist) 35%": metrics["apply_to_shortlist_rate"],
            "Supply Health (active listings) 30%": min(metrics["active_listings"]/300*100,100),
            "Discovery (search→view rate) 20%": metrics["search_to_view_rate"],
            "Verification Quality 15%": metrics["verification_pass_rate"],
        }
        comp_df = pd.DataFrame({"Component":list(components.keys()),
                                 "Score":[round(v,1) for v in components.values()]})
        fig_comp = px.bar(comp_df, x="Score", y="Component", orientation="h",
                          color="Score", range_color=[0,100],
                          color_continuous_scale=["#fee2e2","#fef9c3","#dcfce7"])
        fig_comp.add_vline(x=70, line_dash="dash", line_color="#888",
                           annotation_text="Target 70")
        fig_comp.update_layout(height=240,margin=dict(t=10,b=10),coloraxis_showscale=False)
        st.plotly_chart(fig_comp, use_container_width=True)

    st.divider()

    # ── four metric groups ────────────────────────────────
    st.subheader("📦 Supply Health")
    s1,s2,s3,s4 = st.columns(4)
    s1.metric("Active Listings",     fmt(metrics["active_listings"]),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["active_listings"]["decision"])
    s2.metric("Jobs Posted (7d)",    fmt(metrics["jobs_posted_last_7d"]),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["jobs_posted_last_7d"]["decision"])
    s3.metric("Avg Min CGPA",        fmt(metrics["avg_min_cgpa_threshold"]),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["avg_min_cgpa_threshold"]["decision"])
    s4.metric("Supply WoW Growth",
              fmt(metrics["supply_growth_wow"], "%") if metrics["supply_growth_wow"] is not None else "N/A",
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["supply_growth_wow"]["decision"])

    st.subheader("🔍 Discovery")
    d1,d2,d3,d4 = st.columns(4)
    d1.metric("Search→View Rate",   fmt(metrics["search_to_view_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["search_to_view_rate"]["decision"])
    d2.metric("Search Latency p95", fmt(metrics["search_latency_p95"], "ms"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["search_latency_p95"]["decision"])
    d3.metric("Zero Result Rate",   fmt(metrics["zero_result_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["zero_result_rate"]["decision"])
    d4.metric("Avg Fit Score",      fmt(metrics["avg_fit_score"], "/100"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["avg_fit_score"]["decision"])

    st.subheader("📝 Application Funnel")
    a1,a2,a3,a4 = st.columns(4)
    a1.metric("Verification Pass Rate",    fmt(metrics["verification_pass_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["verification_pass_rate"]["decision"])
    a2.metric("Apply→Shortlist Rate",      fmt(metrics["apply_to_shortlist_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["apply_to_shortlist_rate"]["decision"])
    a3.metric("Shortlist→Interview Rate",  fmt(metrics["shortlist_to_interview_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["shortlist_to_interview_rate"]["decision"])
    a4.metric("Interview→Offer Rate",      fmt(metrics["interview_to_offer_rate"], "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["interview_to_offer_rate"]["decision"])

    st.subheader("🛡️ Integrity")
    i1, i2 = st.columns(2)
    si = metrics["shortlist_integrity"]
    i1.metric("Shortlist Integrity", fmt(si, "%"),
              help=ctx.LIQUIDITY_METRIC_DICTIONARY["shortlist_integrity"]["decision"])
    if si == 100.0:
        i2.success("✅ No unverified candidate ever shortlisted")
    else:
        i2.error(f"🔴 {100-si:.1f}% of shortlists breached integrity — investigate immediately")

    st.divider()

    # ── end-to-end chain bar chart ────────────────────────
    st.subheader("End-to-End Flow: Company Posts → Student Applies → Company Shortlists")
    chain_df = pd.DataFrame({
        "stage": ["Posted","Viewed","Applied","Verified","Shortlisted","Interviewed","Offered"],
        "count": [
            ctx.q("SELECT COUNT(*) n FROM job_supply_events").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM job_view_events").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM applications").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM applications WHERE verified=1").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM applications WHERE status IN ('Shortlisted','Interviewed','Offered')").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM applications WHERE status IN ('Interviewed','Offered')").iloc[0,0],
            ctx.q("SELECT COUNT(*) n FROM applications WHERE status='Offered'").iloc[0,0],
        ]
    })
    fig_chain = go.Figure(go.Funnel(
        y=chain_df["stage"], x=chain_df["count"],
        textinfo="value+percent initial",
        marker=dict(color=["#1e2761","#3b5bdb","#6b8cfa","#a5b4fc",
                           "#fbbf24","#fb923c","#22c55e"])
    ))
    fig_chain.update_layout(title="Full Marketplace Funnel (real data — every stage sourced from events)",
                            height=420, margin=dict(t=40,b=10))
    st.plotly_chart(fig_chain, use_container_width=True)

    st.divider()

    # ── metric dictionary ─────────────────────────────────
    st.subheader("📖 Metric Dictionary — every number, its source, its decision")
    st.caption("If a number can't be traced to a source and forward to a decision, it doesn't appear here.")
    rows = []
    for name, defn in ctx.LIQUIDITY_METRIC_DICTIONARY.items():
        rows.append({
            "Metric": name,
            "Live Value": fmt(metrics.get(name)),
            "Definition": defn["definition"][:80],
            "Source": defn["source"],
            "Decision": defn["decision"][:90],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=480)


    # ═══════════════════════════════════════════════════════
    # TAB 1 — REVENUE METRICS (Task 6 centrepiece)
    # ═══════════════════════════════════════════════════════
