"""
Task 1 — Marketplace Overview
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task01(ctx):
    """Render the "Task 1 — Marketplace Overview" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """

    # ── top KPI cards ────────────────────────────────────
    total_companies = ctx.q("SELECT COUNT(*) n FROM companies").iloc[0,0]
    total_jobs      = ctx.q("SELECT COUNT(*) n FROM jobs").iloc[0,0]
    total_students  = ctx.q("SELECT COUNT(*) n FROM students").iloc[0,0]
    total_apps      = ctx.q("SELECT COUNT(*) n FROM applications").iloc[0,0]
    shortlisted     = ctx.q("SELECT COUNT(*) n FROM applications WHERE status='Shortlisted'").iloc[0,0]
    interviewed     = ctx.q("SELECT COUNT(*) n FROM interviews").iloc[0,0]
    offered         = ctx.q("SELECT COUNT(*) n FROM offers").iloc[0,0]

    shortlist_rate  = round(shortlisted / total_apps * 100, 1) if total_apps else 0
    interview_rate  = round(interviewed / max(shortlisted,1) * 100, 1)
    offer_rate      = round(offered / max(interviewed,1) * 100, 1)

    avg_time = ctx.q("""
        SELECT AVG((JULIANDAY(o.offered_at) - JULIANDAY(a.applied_at))) avg_days
        FROM offers o JOIN applications a ON o.application_id = a.application_id
    """).iloc[0,0]
    avg_time = round(avg_time, 1) if avg_time else "—"

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🏢 Companies",    total_companies)
    c2.metric("💼 Jobs",         total_jobs)
    c3.metric("🎓 Students",     total_students)
    c4.metric("📝 Applications", total_apps)

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("🎯 Shortlist Rate",  f"{shortlist_rate}%")
    c6.metric("🗣️ Interview Rate",  f"{interview_rate}%")
    c7.metric("🏆 Offer Rate",      f"{offer_rate}%")
    c8.metric("⏱️ Avg Time to Hire", f"{avg_time} days")

    st.divider()

    # ── hiring funnel ─────────────────────────────────────
    col_f, col_p = st.columns(2)

    with col_f:
        funnel_df = pd.DataFrame({
            "stage": ["Applied", "Shortlisted", "Interviewed", "Offered"],
            "count": [total_apps, shortlisted, interviewed, offered]
        })
        fig_funnel = go.Figure(go.Funnel(
            y=funnel_df["stage"], x=funnel_df["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#1e2761","#3b5bdb","#6b8cfa","#22c55e"])
        ))
        fig_funnel.update_layout(title="Hiring Funnel", height=320,
                                  margin=dict(t=40,b=10,l=10,r=10))
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_p:
        status_df = ctx.q("""
            SELECT status, COUNT(*) count FROM applications GROUP BY status
        """)
        fig_pie = px.pie(status_df, names="status", values="count",
                         title="Application Status Mix",
                         color_discrete_sequence=px.colors.qualitative.Bold)
        fig_pie.update_layout(height=320, margin=dict(t=40,b=10,l=10,r=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # ── time-series: applications + jobs per day ──────────
    col_a, col_b = st.columns(2)

    with col_a:
        apps_daily = ctx.q("""
            SELECT DATE(applied_at) date, COUNT(*) applications
            FROM applications
            GROUP BY DATE(applied_at) ORDER BY date
        """)
        fig_apps = px.line(apps_daily, x="date", y="applications",
                           title="Applications Per Day",
                           color_discrete_sequence=["#3b5bdb"])
        fig_apps.update_layout(height=280, margin=dict(t=40,b=10,l=10,r=10))
        st.plotly_chart(fig_apps, use_container_width=True)

    with col_b:
        co_growth = ctx.q("""
            SELECT DATE(created_at) date, COUNT(*) companies
            FROM companies GROUP BY DATE(created_at) ORDER BY date
        """)
        fig_co = px.line(co_growth, x="date", y="companies",
                         title="Company Signups Per Day",
                         color_discrete_sequence=["#f59e0b"])
        fig_co.update_layout(height=280, margin=dict(t=40,b=10,l=10,r=10))
        st.plotly_chart(fig_co, use_container_width=True)

    # ── top skills in demand ──────────────────────────────
    skills_raw = ctx.q("SELECT skills FROM jobs")
    from collections import Counter
    all_skills = []
    for row in skills_raw["skills"].dropna():
        all_skills.extend([s.strip() for s in row.split(",")])
    skill_counts = pd.DataFrame(Counter(all_skills).most_common(12),
                                 columns=["skill","count"])
    fig_skills = px.bar(skill_counts, x="count", y="skill", orientation="h",
                        title="Top Skills In Demand (from job postings)",
                        color="count", color_continuous_scale="Blues")
    fig_skills.update_layout(height=380, margin=dict(t=40,b=10,l=10,r=10),
                              coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_skills, use_container_width=True)

    # ── jobs by company ───────────────────────────────────
    company_jobs = ctx.q("""
        SELECT c.company_name, COUNT(j.job_id) jobs
        FROM companies c LEFT JOIN jobs j ON c.company_id=j.company_id
        GROUP BY c.company_name ORDER BY jobs DESC LIMIT 15
    """)
    fig_co_jobs = px.bar(company_jobs, x="jobs", y="company_name", orientation="h",
                          title="Jobs Posted By Company (top 15)",
                          color_discrete_sequence=["#1e2761"])
    fig_co_jobs.update_layout(height=420, margin=dict(t=40,b=10,l=10,r=10),
                               yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_co_jobs, use_container_width=True)


    # ═══════════════════════════════════════════════════════
    # TAB 2 — JOB SUPPLY (Task 2 centrepiece)
    # ═══════════════════════════════════════════════════════
