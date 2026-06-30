"""
PlaceMux Analytics Dashboard — main entry point.

This file is intentionally thin. All the actual UI/logic for each task
lives in its own file under tabs/, e.g. tabs/task12_time_to_hire.py.
This file just:
  1. builds the shared AppContext (cached DB/engine access — core/context.py)
  2. draws the page header
  3. creates the tabs, newest task first (12 down to 1), then
     Validation and Raw Data last
  4. calls each tab module's render_taskNN(ctx) function

Run: streamlit run dashboard.py

To add/change a task tab:
  - edit its file inside tabs/ (one file per task, see TAB_REGISTRY below)
  - nothing else in this file needs to change
"""
import os
import streamlit as st

from core.context import AppContext
from tabs.task13_offer_acceptance import render_task13
from tabs.task12_time_to_hire import render_task12
from tabs.task11_offer_funnel import render_task11
from tabs.task10_revenue_command_center import render_task10
from tabs.task09_arpu_cohorts import render_task09
from tabs.task08_refunds import render_task08
from tabs.task07_conversion import render_task07
from tabs.task06_revenue import render_task06
from tabs.task05_liquidity import render_task05
from tabs.task04_application_funnel import render_task04
from tabs.task03_company_funnel import render_task03
from tabs.task02_job_supply import render_task02
from tabs.task01_overview import render_task01
from tabs.validation_all_tasks import render_validation
from tabs.raw_data_explorer import render_raw_data

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

st.set_page_config(page_title="PlaceMux Dashboard", page_icon="📊", layout="wide")

# Tab order: Task 12 first, counting down to Task 1, then Validation, then Raw Data.
# (label, render function)
TAB_REGISTRY = [
    ("✅ Offer→Acceptance (Task 13)",         render_task13),
    ("⏱️ Time-to-Hire (Task 12)",            render_task12),
    ("📋 Offer Funnel & E-Sign (Task 11)",   render_task11),
    ("🏦 Revenue Command Center (Task 10)",  render_task10),
    ("📈 ARPU & Cohorts (Task 9)",           render_task09),
    ("🔄 Refunds (Task 8)",                  render_task08),
    ("🔁 Conversion (Task 7)",               render_task07),
    ("💰 Revenue (Task 6)",                  render_task06),
    ("💧 Liquidity (Task 5)",                render_task05),
    ("📝 Application Funnel (Task 4)",       render_task04),
    ("🏢 Company Funnel (Task 3)",           render_task03),
    ("📦 Job Supply (Task 2)",               render_task02),
    ("🏠 Overview (Task 1)",                 render_task01),
    ("🔍 Validation",                        render_validation),
    ("📋 Raw Data",                          render_raw_data),
]


def main():
    ctx = AppContext(DB)

    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#1e2761,#3b5bdb);padding:1.2rem 2rem;
                border-radius:12px;margin-bottom:1.2rem'>
      <h1 style='color:#fff;margin:0;font-size:1.8rem'>📊 PlaceMux Marketplace Dashboard</h1>
      <p style='color:#cadcfc;margin:0.25rem 0 0'>Phase 2 · Week 3–4 · Tasks 1–13 &nbsp;|&nbsp;
      As of {ctx.TODAY.strftime('%d %b %Y')}</p>
    </div>""", unsafe_allow_html=True)

    labels = [label for label, _ in TAB_REGISTRY]
    tabs = st.tabs(labels)

    for tab, (_, render_fn) in zip(tabs, TAB_REGISTRY):
        with tab:
            render_fn(ctx)


main()
