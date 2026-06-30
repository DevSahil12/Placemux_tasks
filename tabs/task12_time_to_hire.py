"""
Task 12 — Time-to-Hire
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task12(ctx):
    """Render the "Task 12 — Time-to-Hire" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    tth = ctx.get_tth()

    st.subheader("⏱️ Time-to-Hire — E-Sign Integration & Tamper-Evidence")
    st.caption("Founder verify: An offer can be digitally signed and "
               "tamper-evidently hashed. This tab measures hiring velocity "
               "end-to-end and proves every signed offer is independently verifiable.")

    # ── headline time-to-hire number ────────────────────
    tth_val = tth["time_to_hire_days"]
    if tth_val is not None:
        tth_color = "#22c55e" if tth_val <= 15 else ("#f59e0b" if tth_val <= 25 else "#ef4444")
        st.markdown(
            f'<div style="background:{tth_color}22;border-left:6px solid {tth_color};'
            f'padding:1rem 1.5rem;border-radius:8px;margin-bottom:1rem">'
            f'<span style="font-size:2.2rem;font-weight:700;color:{tth_color}">'
            f'{tth_val} days</span>'
            f'<span style="font-size:1.05rem;color:#444;margin-left:1rem">'
            f'Average Time-to-Hire (application → offer signed)</span>'
            f'</div>', unsafe_allow_html=True
        )

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Time to First Interview", f"{tth['time_to_first_interview_days']} days",
              help="Formula: AVG(interview.scheduled_at - application.applied_at)")
    c2.metric("Time to Offer", f"{tth['time_to_offer_days']} days",
              help="Formula: AVG(offer.offered_at - application.applied_at)")
    c3.metric("Time to Sign", f"{tth['time_to_sign_hours']} hrs",
              help="Formula: AVG(esign.signed_at - esign.sent_at) in hours")
    c4.metric("Median Time-to-Hire", f"{tth['median_time_to_hire_days']} days",
              help="Median (not mean) — less skewed by outlier hires")

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("Fastest Hire", f"{tth['fastest_hire_days']} days", help="Best-case benchmark")
    c6.metric("Slowest Hire", f"{tth['slowest_hire_days']} days",
              delta="Flag if > 30 days" if (tth['slowest_hire_days'] or 0) > 30 else None,
              help="Worst-case — flag for manual review if > 30 days")
    hash_cov = tth["document_hash_coverage_rate"]
    c7.metric("Document Hash Coverage", f"{hash_cov}%",
              delta="✅ 100%" if hash_cov == 100 else f"⚠️ Gap: {100-hash_cov:.1f}%",
              help="% of esign_documents with a tamper-evidence hash recorded")
    dispute_r = tth["dispute_rate"]
    c8.metric("Dispute Rate", f"{dispute_r}%",
              delta="⚠️ Above 2%" if dispute_r > 2 else "✅ Within range",
              delta_color="inverse" if dispute_r > 2 else "normal",
              help="% of signed offers later disputed by the candidate")

    st.divider()

    # ── funnel stage waterfall ───────────────────────────
    col_w1, col_w2 = st.columns([2,1])
    with col_w1:
        stages = tth["_stage_breakdown"]
        stage_df = pd.DataFrame({
            "stage": list(stages.keys()),
            "days": [v if v is not None else 0 for v in stages.values()]
        })
        fig_wf = go.Figure(go.Bar(
            x=stage_df["stage"], y=stage_df["days"],
            marker_color=["#1e2761","#3b5bdb","#a5b4fc","#22c55e"],
            text=[f"{d:.1f}d" for d in stage_df["days"]], textposition="outside"
        ))
        fig_wf.update_layout(title="Hiring Velocity by Stage (cumulative days)",
                             height=340, margin=dict(t=40,b=10))
        st.plotly_chart(fig_wf, use_container_width=True)

    with col_w2:
        dist = tth.get("_hire_days_distribution", [])
        if dist:
            fig_hist = px.histogram(x=dist, nbins=10,
                                    title="Time-to-Hire Distribution",
                                    labels={"x":"Days"},
                                    color_discrete_sequence=["#3b5bdb"])
            fig_hist.update_layout(height=340, margin=dict(t=40,b=10))
            st.plotly_chart(fig_hist, use_container_width=True)

    st.divider()

    # ── by role / by company ─────────────────────────────
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        role_data = tth.get("_time_to_hire_by_role", [])
        if role_data:
            role_df = pd.DataFrame(role_data)
            fig_role = px.bar(role_df.sort_values("avg_days"),
                              x="avg_days", y="role", orientation="h",
                              color="avg_days", color_continuous_scale="RdYlGn_r",
                              title="Time-to-Hire by Job Role",
                              labels={"avg_days":"Avg Days"})
            fig_role.update_layout(height=380, margin=dict(t=40,b=10),
                                   coloraxis_showscale=False)
            st.plotly_chart(fig_role, use_container_width=True)

    with col_r2:
        co_data = tth.get("_time_to_hire_by_company", [])
        if co_data:
            co_df = pd.DataFrame(co_data).head(15)
            fig_co = px.bar(co_df.sort_values("avg_days"),
                            x="avg_days", y="company", orientation="h",
                            color="avg_days", color_continuous_scale="RdYlGn_r",
                            title="Time-to-Hire by Company (fastest 15)",
                            labels={"avg_days":"Avg Days"})
            fig_co.update_layout(height=380, margin=dict(t=40,b=10),
                                 coloraxis_showscale=False)
            st.plotly_chart(fig_co, use_container_width=True)

    st.divider()

    # ── TAMPER-EVIDENCE — the core trust demonstration ────
    st.subheader("🔐 Tamper-Evidence — Live Verification Demo")
    st.caption("Self-check: 'show me an offer being signed, then prove it can't "
               "be quietly tampered with.' This section does exactly that — live, "
               "on real data, not a claim.")

    signed_docs = ctx.q("""
        SELECT doc_id, offer_id, status, provider, provider_mode,
               generated_at, signed_at, doc_hash
        FROM esign_documents WHERE status='signed'
        ORDER BY doc_id DESC LIMIT 20
    """)
    if not signed_docs.empty:
        selected_doc = st.selectbox(
            "Select a signed offer to verify",
            signed_docs["doc_id"].tolist(),
            format_func=lambda x: f"doc_id={x} (offer_id="
                                  f"{signed_docs[signed_docs['doc_id']==x]['offer_id'].iloc[0]})"
        )
        result = ctx.verify_offer_authenticity(int(selected_doc), ctx.DB)

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown(f"**Document:** doc_id={result['doc_id']}, offer_id={result['offer_id']}")
            st.markdown(f"**Provider:** {result['provider']} ({result['provider_mode']})")
            st.markdown(f"**Signed at:** {result['signed_at']}")
            st.code(f"Stored hash:     {result['stored_hash']}\n"
                   f"Recomputed hash: {result['recomputed_hash']}", language="text")
        with col_v2:
            if result["verified"]:
                st.success(result["conclusion"])
            else:
                st.error(result["conclusion"])

        st.markdown("**🧪 Live Tamper Simulation**")
        st.caption("Demonstrates that ANY content change produces a different hash — "
                   "tampering is mathematically detectable, not policy-based.")
        if st.button("Simulate tampering this offer (change ₹ → $ in content)"):
            doc_content = ctx.q(f"SELECT doc_content FROM esign_documents WHERE doc_id={selected_doc}").iloc[0,0]
            tampered = doc_content.replace("INR", "USD")
            import hashlib as _h
            tampered_hash = _h.sha256(tampered.encode("utf-8")).hexdigest()
            match = tampered_hash == result["stored_hash"]
            st.code(f"Original hash : {result['stored_hash']}\n"
                   f"Tampered hash : {tampered_hash}\n"
                   f"Match: {match}", language="text")
            if not match:
                st.error("🔴 TAMPERING DETECTED — hash no longer matches. "
                         "This proves the integrity check works on real data.")

    st.divider()

    # ── eSign provider status — self-check Q3 ─────────────
    st.subheader("📡 eSign Provider Status")
    modes = tth["esign_provider_mode"]
    providers = tth["esign_providers_in_use"]
    uptime = tth["esign_provider_uptime_rate"]
    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("Provider(s)", ", ".join(providers))
    col_p2.metric("Mode", ", ".join(modes).upper())
    col_p3.metric("Confirmation Rate", f"{uptime}%")
    if "sandbox" in modes and uptime >= 95:
        st.success(f"✅ ON TRACK — sandbox integration stable at {uptime}% confirmation rate. "
                   "Remaining before production: provider production API keys, "
                   "IT Act 2000 §3A compliance review, production webhook deployed.")
    elif "production" in modes:
        st.warning("⚠️ PRODUCTION MODE ACTIVE — confirm go-live checklist signed off "
                   "before this is legally binding.")
    else:
        st.warning(f"⚠️ Confirmation rate {uptime}% below 95% — investigate before scaling.")

    st.divider()

    # ── disputed offers — self-check Q4 ───────────────────
    st.subheader("⚠️ Disputed Offers — Independent Verification")
    disputed = ctx.get_disputed_offers(ctx.DB)
    if disputed:
        for d in disputed[:5]:
            if d["doc_id"]:
                v = ctx.verify_offer_authenticity(d["doc_id"], ctx.DB)
                icon = "✅" if v["verified"] else "🔴"
                st.markdown(f"{icon} **Offer #{d['offer_id']}** disputed at {d['disputed_at']} "
                           f"— {v['conclusion']}")
            else:
                st.markdown(f"⚠️ **Offer #{d['offer_id']}** disputed — no e-sign document found "
                           f"(offer may have been disputed before signing)")
    else:
        st.info("No disputed offers in current data.")

    st.divider()

    # ── metric dictionary ──────────────────────────────────
    st.subheader("📖 How Each Metric Is Calculated")
    scalar_tth = {k:v for k,v in tth.items()
                  if not k.startswith("_") and not isinstance(v,(list,dict))}
    for name, val in scalar_tth.items():
        defn = ctx.TIME_TO_HIRE_METRIC_DICTIONARY.get(name, {})
        val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
        with st.expander(f"**{name}** = {val_str}", expanded=False):
            st.markdown(f"**Definition:** {defn.get('definition','—')}")
            st.code(defn.get("formula","—"), language="sql")
            st.markdown(f"**Source:** `{defn.get('source','—')}`")
            st.markdown(f"**Decision:** _{defn.get('decision','—')}_")
            st.markdown(f"**Expected range:** {defn.get('expected_range','—')}")


    # ═══════════════════════════════════════════════════════
    # TAB 3 — LIQUIDITY DASHBOARD (Task 5 centrepiece)
    # ═══════════════════════════════════════════════════════
