"""
Raw Data Explorer
Rendering logic for this tab, extracted into its own module so the
main dashboard.py stays a thin router instead of one giant file.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_raw_data(ctx):
    """Render the "Raw Data Explorer" tab.

    `ctx` is the shared AppContext (see core/context.py) exposing cached
    data-loader functions, the DB path, and constants such as the run timestamp.
    """
    table = st.selectbox("Table", ["applications","jobs","students","companies","interviews",
                                   "offers","job_supply_events","job_search_events",
                                   "job_view_events","application_events",
                                   "payments","payment_events","payment_reconciliation",
                                   "student_payments","conversion_events",
                                   "receipts","refunds","refund_events",
                                   "offer_events","esign_documents","esign_events"])
    st.dataframe(ctx.q(f"SELECT * FROM {table}"), use_container_width=True, height=500)
