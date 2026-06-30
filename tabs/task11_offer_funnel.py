"""
Task 11 — Offer Funnel & E-Sign
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_task11(ctx):
    """Render the "Task 11 — Offer Funnel & E-Sign" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """

    om = ctx.get_offer()
    oc = ctx.get_offer_checks()
    all_pass_o = all(v["result"] in ("PASS","WARN") for v in oc.values())
    banner_col = "#16a34a" if all_pass_o else "#dc2626"

    st.markdown(
        f'''<div style="background:linear-gradient(90deg,#1e40af,#0891b2);
        padding:1.2rem 2rem;border-radius:12px;margin-bottom:1rem">
        <h2 style="color:#fff;margin:0;font-size:1.5rem">&#128203; Offer Funnel & E-Sign Metrics</h2>
        <p style="color:#bae6fd;margin:0.3rem 0 0">Task 11 · Offer Generation &amp; E-Sign Design ·
        <span style="background:''' + banner_col + '''22;border:1px solid ''' + banner_col + ''';
        color:''' + banner_col + ''';padding:2px 10px;border-radius:4px;font-weight:700">
        {"ALL CHECKS PASS" if all_pass_o else "ISSUES DETECTED"}</span></p></div>''',
        unsafe_allow_html=True)

    # ── ROW 1: Funnel KPIs ────────────────────────────────
    st.subheader("&#128202; Offer Funnel — Conversion Rates")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Shortlist → Interview",
              f"{om['shortlist_to_interview_rate']}%",
              help=ctx.OFFER_METRIC_DICTIONARY['shortlist_to_interview_rate']['decision'])
    k2.metric("Interview → Offer",
              f"{om['interview_to_offer_rate']}%",
              help=ctx.OFFER_METRIC_DICTIONARY['interview_to_offer_rate']['decision'])
    k3.metric("Offer Acceptance",
              f"{om['offer_acceptance_rate']}%",
              delta="⚠️ <65%" if om['offer_acceptance_rate'] < 65 else "✅ On target",
              delta_color="inverse" if om['offer_acceptance_rate'] < 65 else "normal",
              help=ctx.OFFER_METRIC_DICTIONARY['offer_acceptance_rate']['decision'])
    k4.metric("Accept → E-Signed",
              f"{om['offer_to_sign_rate']}%",
              help=ctx.OFFER_METRIC_DICTIONARY['offer_to_sign_rate']['decision'])

    # ── Funnel waterfall ──────────────────────────────────
    df_funnel = pd.DataFrame(om["funnel_stages"])
    fig_f = go.Figure(go.Funnel(
        y=df_funnel["stage"],
        x=df_funnel["count"],
        textposition="inside",
        textinfo="value+percent previous",
        marker_color=["#3b5bdb","#0891b2","#0d9488","#16a34a","#ca8a04","#dc2626"],
        connector={"line": {"color": "#e2e8f0", "width": 2}},
    ))
    fig_f.update_layout(height=320, margin=dict(t=10,b=10,l=10,r=10))
    st.plotly_chart(fig_f, use_container_width=True)

    st.divider()

    # ── ROW 2: Velocity + Counts ──────────────────────────
    st.subheader("&#9201; Velocity & Stage Counts")
    v1, v2, v3, v4, v5, v6 = st.columns(6)
    v1.metric("Total Offers",    str(om["total_offers"]))
    v2.metric("Accepted",        str(om["offers_accepted"]))
    v3.metric("E-Signed",        str(om["total_signed"]))
    v4.metric("Days Apply→Offer", f"{om['avg_days_apply_to_offer']}d",
              help=ctx.OFFER_METRIC_DICTIONARY['avg_days_apply_to_offer']['decision'])
    v5.metric("Hours Offer→Sign", f"{om['avg_hours_offer_to_sign']}h",
              help=ctx.OFFER_METRIC_DICTIONARY['avg_hours_offer_to_sign']['decision'])
    v6.metric("Hours Sent→Viewed", f"{om['avg_hours_sent_to_viewed']}h",
              help=ctx.OFFER_METRIC_DICTIONARY['avg_hours_sent_to_viewed']['decision'])

    st.divider()

    # ── ROW 3: E-Sign Status + Integrity ─────────────────
    col_esign, col_hash = st.columns(2)

    with col_esign:
        st.markdown("#### &#128221; E-Sign Document Status")
        if om["esign_status_breakdown"]:
            df_es = pd.DataFrame(om["esign_status_breakdown"])
            fig_es = px.pie(df_es, names="status", values="count",
                            color_discrete_sequence=px.colors.qualitative.Set2)
            fig_es.update_layout(height=220, margin=dict(t=10,b=10))
            st.plotly_chart(fig_es, use_container_width=True)
        st.markdown(f"**Provider:** {om['esign_provider']}  "
                    f"**Mode:** `{om['esign_provider_mode']}`")
        with st.expander("How it's calculated"):
            st.caption(f"**Source:** esign_documents table — one row per offer letter")
            st.caption(f"**Decision:** {ctx.OFFER_METRIC_DICTIONARY['esign_provider_mode']['decision']}")

    with col_hash:
        st.markdown("#### &#128274; Tamper-Evidence & Authenticity")
        h1c, h2c = st.columns(2)
        hash_ok = om["tamper_evidence_coverage_pct"] == 100.0
        intact_ok = om["documents_with_intact_hash_pct"] == 100.0
        h1c.metric("Hash Coverage",
                   f"{om['tamper_evidence_coverage_pct']}%",
                   delta="✅ All signed docs hashed" if hash_ok else "❌ Gaps detected",
                   help=ctx.OFFER_METRIC_DICTIONARY['tamper_evidence_coverage_pct']['decision'])
        h2c.metric("Hash Intact (verified)",
                   f"{om['documents_with_intact_hash_pct']}%",
                   delta=f"✅ {om['documents_verified_intact']} docs recomputed & match" if intact_ok
                         else "❌ TAMPERED — security incident",
                   help=ctx.OFFER_METRIC_DICTIONARY['documents_with_intact_hash_pct']['decision'])
        st.markdown("""
        **How tamper-evidence works:**
        1. When candidate signs → SHA-256 hash of the offer letter text is computed and stored
        2. To verify authenticity → recompute hash from stored doc_content, compare to stored doc_hash
        3. If they match → document is provably unaltered since signing
        4. If they differ → document was modified after signing → security incident
        """)
        with st.expander("Self-check: Can we prove an offer is authentic?"):
            st.code("""
    -- Verify any specific offer letter:
    SELECT doc_id, offer_id, status, doc_hash,
       CASE WHEN doc_hash IS NOT NULL THEN 'Hash stored — verifiable'
            ELSE 'No hash — cannot verify' END AS authenticity
    FROM esign_documents WHERE offer_id = ?;

    -- Full tamper audit:
    SELECT COUNT(*) verified_intact
    FROM esign_documents
    WHERE status = 'signed'
      AND doc_hash = hex(sha256(doc_content));  -- recompute and compare
            """, language="sql")

    st.divider()

    # ── ROW 4: Risk flags ─────────────────────────────────
    st.subheader("&#9888;&#65039; Risk Flags & Actionable Items")
    rf1, rf2, rf3 = st.columns(3)

    unsigned = om["unsigned_accepted_offers_count"]
    rf1.metric("Unsigned Accepted Offers",
               str(unsigned),
               delta="⚠️ Chase within 24h" if unsigned > 0 else "✅ Clean",
               delta_color="inverse" if unsigned > 0 else "normal",
               help=ctx.OFFER_METRIC_DICTIONARY['unsigned_accepted_offers_count']['decision'])

    rf2.metric("Disputed Offers",
               str(om["disputed_offers_count"]),
               delta=f"Resolved: {om['disputes_resolved_count']} ({om['dispute_resolution_rate_pct']}%)",
               help=ctx.OFFER_METRIC_DICTIONARY['disputed_offers_count']['decision'])

    rf3.metric("Offer Declines",
               str(om["total_declines"]),
               help=ctx.OFFER_METRIC_DICTIONARY['offer_decline_reasons']['decision'])

    # Decline reasons breakdown
    if om["offer_decline_reasons"]:
        with st.expander("Decline Reason Breakdown (decision-grade)"):
            df_dr = pd.DataFrame(om["offer_decline_reasons"])
            total_d = om["total_declines"]
            df_dr["pct"] = (df_dr["count"] / max(total_d, 1) * 100).round(1)
            fig_dr = px.bar(df_dr, x="count", y="decline_reason", orientation="h",
                            color="count", color_continuous_scale=["#dbeafe","#1e40af"],
                            labels={"decline_reason":"Reason","count":"Declines"})
            fig_dr.update_layout(height=180, margin=dict(t=10,b=10), coloraxis_showscale=False)
            st.plotly_chart(fig_dr, use_container_width=True)
            top = om["offer_decline_reasons"][0]["decline_reason"]
            if top == "salary_too_low":
                st.warning("⚠️ **salary_too_low** is the top decline reason → run salary benchmarking before next offer batch.")
            elif top == "competing_offer":
                st.warning("⚠️ **competing_offer** is the top decline reason → reduce time-to-offer (target < 10 days).")
            for md_key in ["offer_decline_reasons"]:
                st.caption(f"**Decision:** {ctx.OFFER_METRIC_DICTIONARY[md_key]['decision']}")

    st.divider()

    # ── ROW 5: Validation checks ──────────────────────────
    st.subheader("&#128269; Task 11 Validation (6 Checks)")
    for name, res in oc.items():
        icon  = "✅" if res["result"]=="PASS" else ("⚠️" if res["result"]=="WARN" else "❌")
        color = "#dcfce7" if res["result"]=="PASS" else ("#fef9c3" if res["result"]=="WARN" else "#fee2e2")
        st.markdown(
            f'''<div style="background:{color};padding:0.5rem 1rem;border-radius:6px;margin:3px 0">
            {icon} <strong>{res["result"]}</strong> — {name.replace("_"," ")}
            <span style="color:#555;font-size:0.85rem"> · {res["detail"]}</span></div>''',
            unsafe_allow_html=True)

    if all_pass_o:
        st.success("✅ ALL TASK 11 CHECKS PASS — Offer funnel metrics defined, "
                   "e-sign integrity verified, demoable end-to-end.")

    # ── E-sign mode pill ──────────────────────────────────
    mode = om["esign_provider_mode"]
    mode_col = "#f59e0b" if mode == "sandbox" else "#dc2626"
    st.markdown(
        f'''<div style="margin-top:0.8rem">
        <span style="background:{mode_col};color:#fff;padding:4px 16px;border-radius:12px;font-weight:700">
        &#9889; E-SIGN: {mode.upper()} MODE</span>
        &nbsp;&nbsp;<em style="color:#666;font-size:0.85rem">
        {"Sandbox — safe to demo. Production requires: IT Act 2000 §5 compliance · DPDP consent · legal entity binding"
         if mode=="sandbox" else "PRODUCTION — legally binding signatures"}</em>
        </div>''', unsafe_allow_html=True)


    # ═══════════════════════════════════════════════════════
    # TAB 2 — TIME-TO-HIRE (Task 12 centrepiece)
    # ═══════════════════════════════════════════════════════
