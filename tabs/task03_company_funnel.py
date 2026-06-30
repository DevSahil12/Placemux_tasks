"""
Task 3 — Company Funnel
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task03(ctx):
    """Render the "Task 3 — Company Funnel" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    st.subheader("Company Funnel — Search & Discovery")
    st.caption("Posted → Viewed → Applied → Shortlisted → Interviewed → Offered, "
               "built from job_supply_events, job_view_events, applications, "
               "interviews, and offers. This is the Task 3 deliverable — "
               "the founder can open this and explain every number.")

    funnel_agg = ctx.q("""
        WITH posted AS (SELECT job_id FROM job_supply_events),
        viewed AS (SELECT job_id, COUNT(*) n FROM job_view_events GROUP BY job_id),
        applied AS (SELECT job_id, COUNT(*) n FROM applications GROUP BY job_id),
        shortlisted AS (SELECT job_id, COUNT(*) n FROM applications WHERE status='Shortlisted' GROUP BY job_id),
        interviewed AS (
            SELECT a.job_id, COUNT(*) n FROM interviews i
            JOIN applications a ON i.application_id=a.application_id GROUP BY a.job_id),
        offered AS (
            SELECT a.job_id, COUNT(*) n FROM offers o
            JOIN applications a ON o.application_id=a.application_id GROUP BY a.job_id)
        SELECT
            COUNT(DISTINCT p.job_id) jobs_posted,
            COALESCE(SUM(v.n),0) total_views,
            COALESCE(SUM(ap.n),0) total_applications,
            COALESCE(SUM(s.n),0) total_shortlisted,
            COALESCE(SUM(iv.n),0) total_interviewed,
            COALESCE(SUM(o.n),0) total_offered
        FROM posted p
        LEFT JOIN viewed v ON p.job_id=v.job_id
        LEFT JOIN applied ap ON p.job_id=ap.job_id
        LEFT JOIN shortlisted s ON p.job_id=s.job_id
        LEFT JOIN interviewed iv ON p.job_id=iv.job_id
        LEFT JOIN offered o ON p.job_id=o.job_id
    """).iloc[0]

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("📦 Posted", int(funnel_agg["jobs_posted"]))
    c2.metric("👁️ Viewed", int(funnel_agg["total_views"]))
    c3.metric("📝 Applied", int(funnel_agg["total_applications"]))
    c4.metric("⭐ Shortlisted", int(funnel_agg["total_shortlisted"]))
    c5.metric("🗣️ Interviewed", int(funnel_agg["total_interviewed"]))
    c6.metric("🏆 Offered", int(funnel_agg["total_offered"]))

    st.divider()

    funnel_df = pd.DataFrame({
        "stage": ["Posted","Viewed","Applied","Shortlisted","Interviewed","Offered"],
        "count": [funnel_agg["jobs_posted"], funnel_agg["total_views"],
                 funnel_agg["total_applications"], funnel_agg["total_shortlisted"],
                 funnel_agg["total_interviewed"], funnel_agg["total_offered"]]
    })
    fig_cf = go.Figure(go.Funnel(
        y=funnel_df["stage"], x=funnel_df["count"],
        textinfo="value+percent initial",
        marker=dict(color=["#1e2761","#3b5bdb","#6b8cfa","#a5b4fc","#fbbf24","#22c55e"])
    ))
    fig_cf.update_layout(title="Aggregate Company Funnel (all companies)", height=380,
                         margin=dict(t=40,b=10))
    st.plotly_chart(fig_cf, use_container_width=True)

    st.divider()
    st.subheader("Per-Company Funnel")
    st.caption("Select a company to see exactly where their candidates drop off — "
               "this is the decision-grade view a company admin would actually use.")

    company_list = ctx.q("SELECT DISTINCT company_name FROM companies ORDER BY company_name")["company_name"].tolist()
    selected_co = st.selectbox("Company", company_list)

    co_funnel = ctx.q(f"""
        SELECT
            COUNT(DISTINCT j.job_id) jobs_posted,
            COUNT(DISTINCT v.view_id) views,
            COUNT(DISTINCT a.application_id) applications,
            COUNT(DISTINCT CASE WHEN a.status='Shortlisted' THEN a.application_id END) shortlisted,
            COUNT(DISTINCT i.interview_id) interviewed,
            COUNT(DISTINCT o.offer_id) offered
        FROM companies c
        JOIN jobs j ON c.company_id=j.company_id
        LEFT JOIN job_view_events v ON j.job_id=v.job_id
        LEFT JOIN applications a ON j.job_id=a.job_id
        LEFT JOIN interviews i ON a.application_id=i.application_id
        LEFT JOIN offers o ON a.application_id=o.application_id
        WHERE c.company_name = '{selected_co.replace("'","''")}'
    """).iloc[0]

    co_funnel_df = pd.DataFrame({
        "stage": ["Posted","Viewed","Applied","Shortlisted","Interviewed","Offered"],
        "count": [co_funnel["jobs_posted"], co_funnel["views"], co_funnel["applications"],
                 co_funnel["shortlisted"], co_funnel["interviewed"], co_funnel["offered"]]
    })
    col_cf1, col_cf2 = st.columns([2,1])
    with col_cf1:
        fig_co = go.Figure(go.Funnel(
            y=co_funnel_df["stage"], x=co_funnel_df["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#1e2761","#3b5bdb","#6b8cfa","#a5b4fc","#fbbf24","#22c55e"])
        ))
        fig_co.update_layout(title=f"{selected_co} — Funnel", height=340, margin=dict(t=40,b=10))
        st.plotly_chart(fig_co, use_container_width=True)
    with col_cf2:
        st.markdown("**Drop-off diagnosis**")
        v, a = co_funnel["views"], co_funnel["applications"]
        if v > 0 and a > 0:
            conv = round(a/v*100, 1)
            if conv < 15:
                st.warning(f"View→Apply: {conv}% — low. Job description or fit-ranking likely the issue, not candidate supply.")
            else:
                st.success(f"View→Apply: {conv}% — healthy conversion.")
        s, i = co_funnel["shortlisted"], co_funnel["interviewed"]
        if s > 0:
            conv2 = round(i/s*100, 1) if s else 0
            st.info(f"Shortlist→Interview: {conv2}%")

    st.divider()
    st.subheader("Search → View → Fit Ranking (Discovery layer)")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        fit_dist = ctx.q("SELECT fit_score FROM job_search_events WHERE fit_score IS NOT NULL")
        fig_fit = px.histogram(fit_dist, x="fit_score", nbins=30,
                               title="Distribution of Fit Scores in Search Results",
                               color_discrete_sequence=["#3b5bdb"])
        fig_fit.update_layout(height=300, margin=dict(t=40,b=10))
        st.plotly_chart(fig_fit, use_container_width=True)
    with col_d2:
        lat = ctx.q("SELECT latency_ms FROM job_search_events")
        fig_lat = px.histogram(lat, x="latency_ms", nbins=30,
                               title="Search Latency Distribution",
                               color_discrete_sequence=["#f59e0b"])
        p95 = lat["latency_ms"].quantile(0.95)
        fig_lat.add_vline(x=p95, line_dash="dash", line_color="#ef4444",
                          annotation_text=f"p95: {p95:.0f}ms")
        fig_lat.update_layout(height=300, margin=dict(t=40,b=10))
        st.plotly_chart(fig_lat, use_container_width=True)

    st.subheader("Recent Searches (live)")
    recent = ctx.q("""
        SELECT s.searched_at, st.student_name, s.query, s.result_count,
               s.latency_ms, s.fit_score,
               CASE WHEN s.clicked_job_id IS NOT NULL THEN 'Clicked' ELSE 'Skipped' END AS outcome
        FROM job_search_events s JOIN students st ON s.student_id=st.student_id
        ORDER BY s.searched_at DESC LIMIT 25
    """)
    st.dataframe(recent, use_container_width=True, height=320)


    # ═══════════════════════════════════════════════════════
    # TAB 4 — APPLICATION FUNNEL (Task 4 centrepiece)
    # ═══════════════════════════════════════════════════════
