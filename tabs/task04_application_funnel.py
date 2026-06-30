"""
Task 4 — Application Funnel
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task04(ctx):
    """Render the "Task 4 — Application Funnel" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    st.subheader("Application Funnel — Applications & Shortlisting")
    st.caption("Submitted → Verified/Rejected → Shortlisted → Interviewed → Offered. "
               "Built from application_events (immutable log) — every application is "
               "checked against the job's skill threshold (min_cgpa) at submit time. "
               "Only verified candidates can ever be shortlisted; this is enforced in "
               "code (emit_shortlist), not just convention.")

    funnel_agg = ctx.q("""
        SELECT
            COUNT(*) submitted,
            SUM(CASE WHEN verified=1 THEN 1 ELSE 0 END) verified,
            SUM(CASE WHEN verified=0 THEN 1 ELSE 0 END) rejected,
            SUM(CASE WHEN status='Shortlisted' THEN 1 ELSE 0 END) shortlisted,
            SUM(CASE WHEN status='Interviewed' THEN 1 ELSE 0 END) interviewed,
            SUM(CASE WHEN status='Offered' THEN 1 ELSE 0 END) offered
        FROM applications
    """).iloc[0]

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("📝 Submitted", int(funnel_agg["submitted"]))
    c2.metric("✅ Verified", int(funnel_agg["verified"]))
    c3.metric("❌ Rejected", int(funnel_agg["rejected"]))
    c4.metric("⭐ Shortlisted", int(funnel_agg["shortlisted"]))
    c5.metric("🗣️ Interviewed", int(funnel_agg["interviewed"]))
    c6.metric("🏆 Offered", int(funnel_agg["offered"]))

    verification_rate = round(funnel_agg["verified"] / funnel_agg["submitted"] * 100, 1)
    shortlist_of_verified = round(funnel_agg["shortlisted"] / max(funnel_agg["verified"],1) * 100, 1)

    c7, c8 = st.columns(2)
    c7.metric("Verification Pass Rate", f"{verification_rate}%",
              help="% of submitted applications where the student met the job's min_cgpa "
                   "threshold. Low rate -> search is surfacing jobs to unqualified students "
                   "-> fix fit-ranking, not the threshold.")
    c8.metric("Shortlist Rate (of Verified)", f"{shortlist_of_verified}%",
              help="% of verified applications that got shortlisted. Tells a company "
                   "whether their job is competitive once only qualified candidates are counted.")

    st.divider()

    funnel_df = pd.DataFrame({
        "stage": ["Submitted","Verified","Shortlisted","Interviewed","Offered"],
        "count": [funnel_agg["submitted"], funnel_agg["verified"],
                 funnel_agg["shortlisted"], funnel_agg["interviewed"], funnel_agg["offered"]]
    })
    fig_af = go.Figure(go.Funnel(
        y=funnel_df["stage"], x=funnel_df["count"],
        textinfo="value+percent initial",
        marker=dict(color=["#1e2761","#3b5bdb","#a5b4fc","#fbbf24","#22c55e"])
    ))
    fig_af.update_layout(title="Aggregate Application Funnel (verified path only)", height=380,
                         margin=dict(t=40,b=10))
    st.plotly_chart(fig_af, use_container_width=True)

    st.divider()
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        st.subheader("⚠️ Shortlist Integrity Check")
        violation = ctx.q("SELECT COUNT(*) n FROM applications WHERE status='Shortlisted' AND verified=0").iloc[0,0]
        if violation == 0:
            st.success(f"✅ PASS — 0 unverified candidates have ever been shortlisted. "
                       f"Integrity enforced at write time, not just monitored after the fact.")
        else:
            st.error(f"🔴 FAIL — {violation} unverified candidates were shortlisted. Investigate immediately.")

    with col_i2:
        st.subheader("Verification Outcome Split")
        outcome_df = pd.DataFrame({
            "outcome": ["Verified", "Rejected (below threshold)"],
            "count": [funnel_agg["verified"], funnel_agg["rejected"]]
        })
        fig_out = px.pie(outcome_df, names="outcome", values="count",
                         color_discrete_sequence=["#22c55e","#ef4444"])
        fig_out.update_layout(height=260, margin=dict(t=10,b=10))
        st.plotly_chart(fig_out, use_container_width=True)

    st.divider()
    st.subheader("Per-Job Verification & Shortlist Rates")
    st.caption("Where a job's min_cgpa is filtering out most applicants — "
               "a company-actionable view, not just a vanity number.")
    per_job = ctx.q("""
        SELECT j.job_title, j.min_cgpa,
               COUNT(a.application_id) submitted,
               SUM(CASE WHEN a.verified=1 THEN 1 ELSE 0 END) verified,
               SUM(CASE WHEN a.status='Shortlisted' THEN 1 ELSE 0 END) shortlisted,
               ROUND(100.0*SUM(CASE WHEN a.verified=1 THEN 1 ELSE 0 END)/COUNT(a.application_id),1) verify_pct
        FROM jobs j JOIN applications a ON j.job_id=a.job_id
        GROUP BY j.job_id HAVING submitted >= 3
        ORDER BY submitted DESC LIMIT 15
    """)
    fig_job = px.bar(per_job, x="job_title", y=["verified","submitted"],
                     barmode="overlay", title="Verified vs Submitted by Job (top 15 by volume)",
                     color_discrete_sequence=["#22c55e","#cadcfc"])
    fig_job.update_layout(height=360, margin=dict(t=40,b=10))
    st.plotly_chart(fig_job, use_container_width=True)
    st.dataframe(per_job, use_container_width=True, height=280)

    st.subheader("Recent Application Events (live)")
    recent = ctx.q("""
        SELECT e.emitted_at, st.student_name, j.job_title, c.company_name,
               e.event_name, CASE WHEN e.verified=1 THEN 'Yes' ELSE 'No' END AS verified
        FROM application_events e
        JOIN students st ON e.student_id=st.student_id
        JOIN jobs j ON e.job_id=j.job_id
        JOIN companies c ON e.company_id=c.company_id
        ORDER BY e.emitted_at DESC LIMIT 25
    """)
    st.dataframe(recent, use_container_width=True, height=320)


    # ═══════════════════════════════════════════════════════
    # TAB 5 — VALIDATION (Task 2 + Task 3 + Task 4 checks)
    # ═══════════════════════════════════════════════════════
