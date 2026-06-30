"""
Task 2 — Job Supply
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task02(ctx):
    """Render the "Task 2 — Job Supply" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    st.subheader("Job Supply Instrumentation — Live View")
    st.caption("Every row below comes from a `job_posted` event in the `job_supply_events` table. "
               "This view is the Task 2 deliverable — events validated, jobs-posted view live.")

    # hero numbers
    total_supply   = ctx.q("SELECT COUNT(*) n FROM job_supply_events").iloc[0,0]
    open_jobs      = ctx.q("SELECT COUNT(*) n FROM job_supply_events WHERE status='open'").iloc[0,0]
    filled_jobs    = ctx.q("SELECT COUNT(*) n FROM job_supply_events WHERE status='filled'").iloc[0,0]
    avg_cgpa_th    = ctx.q("SELECT ROUND(AVG(min_cgpa),2) n FROM job_supply_events").iloc[0,0]
    avg_sal        = ctx.q("SELECT ROUND(AVG(salary)/100000.0,2) n FROM job_supply_events").iloc[0,0]
    fill_rate_pct  = round(filled_jobs / total_supply * 100, 1) if total_supply else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📦 Total Jobs Posted",  total_supply)
    c2.metric("🟢 Open",              open_jobs)
    c3.metric("✅ Filled",            filled_jobs)
    c4.metric("📊 Fill Rate",         f"{fill_rate_pct}%")
    c5.metric("🎓 Avg Min CGPA",      avg_cgpa_th)

    st.divider()

    # jobs posted per day (last 30 days)
    daily_supply = ctx.q("""
        SELECT DATE(emitted_at) date, COUNT(*) jobs_posted
        FROM job_supply_events
        WHERE emitted_at >= DATE('2026-06-18', '-30 days')
        GROUP BY DATE(emitted_at) ORDER BY date
    """)
    fig_daily = px.bar(daily_supply, x="date", y="jobs_posted",
                       title="Jobs Posted Per Day (last 30 days) — from job_posted events",
                       color_discrete_sequence=["#1e2761"])
    fig_daily.update_layout(height=300, margin=dict(t=40,b=10))
    st.plotly_chart(fig_daily, use_container_width=True)

    col_r, col_s = st.columns(2)

    with col_r:
        # by role
        by_role = ctx.q("""
            SELECT job_title, COUNT(*) jobs,
                   ROUND(AVG(min_cgpa),2) avg_threshold,
                   ROUND(AVG(salary)/100000.0,2) avg_salary_L
            FROM job_supply_events GROUP BY job_title ORDER BY jobs DESC
        """)
        fig_role = px.bar(by_role, x="jobs", y="job_title", orientation="h",
                          title="Supply by Role", color="avg_threshold",
                          color_continuous_scale="Blues",
                          labels={"avg_threshold":"Avg Min CGPA"})
        fig_role.update_layout(height=340, margin=dict(t=40,b=10),
                               yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_role, use_container_width=True)

    with col_s:
        # CGPA threshold distribution
        cgpa_dist = ctx.q("""
            SELECT min_cgpa, COUNT(*) jobs FROM job_supply_events
            GROUP BY min_cgpa ORDER BY min_cgpa
        """)
        fig_cgpa = px.bar(cgpa_dist, x="min_cgpa", y="jobs",
                          title="Skill Threshold (min CGPA) Distribution",
                          color_discrete_sequence=["#3b5bdb"],
                          labels={"min_cgpa":"Min CGPA Required","jobs":"Jobs"})
        fig_cgpa.update_layout(height=340, margin=dict(t=40,b=10))
        st.plotly_chart(fig_cgpa, use_container_width=True)

    # supply by industry
    by_industry = ctx.q("""
        SELECT c.industry, COUNT(e.job_id) jobs_posted,
               ROUND(AVG(e.salary)/100000.0,2) avg_salary_L
        FROM job_supply_events e JOIN companies c ON e.company_id=c.company_id
        GROUP BY c.industry ORDER BY jobs_posted DESC
    """)
    fig_ind = px.bar(by_industry, x="industry", y="jobs_posted",
                     color="avg_salary_L",
                     title="Job Supply by Industry (avg salary in Lakhs shown as color)",
                     color_continuous_scale="Teal",
                     labels={"avg_salary_L":"Avg Salary (L)"})
    fig_ind.update_layout(height=300, margin=dict(t=40,b=10))
    st.plotly_chart(fig_ind, use_container_width=True)

    # salary vs threshold scatter
    scatter_df = ctx.q("""
        SELECT job_title, min_cgpa, salary, status,
               ROUND(salary/100000.0,1) salary_L
        FROM job_supply_events
    """)
    fig_scat = px.scatter(scatter_df, x="min_cgpa", y="salary_L",
                          color="job_title", symbol="status",
                          title="Salary vs CGPA Threshold (each dot = one job posting)",
                          labels={"min_cgpa":"Min CGPA Required","salary_L":"Salary (Lakhs)"},
                          opacity=0.7)
    fig_scat.update_layout(height=380, margin=dict(t=40,b=10))
    st.plotly_chart(fig_scat, use_container_width=True)

    st.divider()
    st.subheader("Raw Event Log — job_supply_events")
    raw = ctx.q("""
        SELECT e.event_id, e.event_name, e.job_id, c.company_name,
               e.job_title, e.skills, e.min_cgpa,
               ROUND(e.salary/100000.0,2) AS salary_L, e.status, e.emitted_at
        FROM job_supply_events e JOIN companies c ON e.company_id=c.company_id
        ORDER BY e.emitted_at DESC
    """)
    st.dataframe(raw, use_container_width=True, height=360)


    # ═══════════════════════════════════════════════════════
    # TAB 3 — COMPANY FUNNEL (Task 3 centrepiece)
    # ═══════════════════════════════════════════════════════
