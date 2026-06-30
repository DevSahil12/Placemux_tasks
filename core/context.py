"""
Shared application context for the PlaceMux dashboard.

Every tab module (see tabs/) receives one `AppContext` instance (`ctx`).
It centralises:
  - the SQLite query helper `ctx.q(sql)`
  - one cached "get_*" loader per engine (Task 1-12 metric computations)
  - the metric dictionaries used for tooltips / "how it's calculated" boxes
  - shared constants: ctx.DB (db path), ctx.TODAY (run timestamp)

Keeping this in one place means each tabs/taskNN_*.py file only has to
say `ctx.get_tth()` instead of re-importing and re-wrapping every engine.
"""
import os
import sqlite3
import datetime as dt

import streamlit as st
import pandas as pd

from liquidity_engine import compute as _compute_liquidity, health_status, METRIC_DICTIONARY as LIQUIDITY_METRIC_DICTIONARY
from revenue_engine import compute_revenue as _compute_revenue, REVENUE_METRIC_DICTIONARY
from conversion_engine import (
    compute as _compute_conversion,
    get_failure_examples, get_abandonment_examples,
    CONVERSION_METRIC_DICTIONARY,
)
from refund_engine import (
    compute as _compute_refunds,
    get_failed_refunds, get_recent_receipts,
    REFUND_METRIC_DICTIONARY,
)
from arpu_engine import compute as _compute_arpu, ARPU_METRIC_DICTIONARY
from offer_funnel_engine import (
    compute as _compute_offer, validate as _validate_offer,
    OFFER_METRIC_DICTIONARY,
)
from time_to_hire_engine import (
    compute as _compute_tth, verify_offer_authenticity, get_disputed_offers,
    TIME_TO_HIRE_METRIC_DICTIONARY,
)
from revenue_command_center import (
    compute as _compute_rcc, validate as _validate_rcc,
    RCC_METRIC_DICTIONARY,
)
from acceptance_engine import (
    compute as _compute_acceptance, validate as _validate_acceptance,
    public_verify_offer,
    ACCEPTANCE_METRIC_DICTIONARY,
)


class AppContext:
    """Holds the DB path + every cached data-loader the tabs need."""

    def __init__(self, db_path: str):
        self.DB = db_path
        self.TODAY = dt.datetime.now()
        self.dt = dt

        # re-export metric dictionaries so tab modules can do ctx.RCC_METRIC_DICTIONARY
        self.LIQUIDITY_METRIC_DICTIONARY = LIQUIDITY_METRIC_DICTIONARY
        self.REVENUE_METRIC_DICTIONARY = REVENUE_METRIC_DICTIONARY
        self.CONVERSION_METRIC_DICTIONARY = CONVERSION_METRIC_DICTIONARY
        self.REFUND_METRIC_DICTIONARY = REFUND_METRIC_DICTIONARY
        self.ARPU_METRIC_DICTIONARY = ARPU_METRIC_DICTIONARY
        self.OFFER_METRIC_DICTIONARY = OFFER_METRIC_DICTIONARY
        self.TIME_TO_HIRE_METRIC_DICTIONARY = TIME_TO_HIRE_METRIC_DICTIONARY
        self.RCC_METRIC_DICTIONARY = RCC_METRIC_DICTIONARY
        self.ACCEPTANCE_METRIC_DICTIONARY = ACCEPTANCE_METRIC_DICTIONARY

        # re-export helper functions used directly inside tab bodies
        self.health_status = health_status
        self.get_failure_examples = get_failure_examples
        self.get_abandonment_examples = get_abandonment_examples
        self.get_failed_refunds = get_failed_refunds
        self.get_recent_receipts = get_recent_receipts
        self.verify_offer_authenticity = verify_offer_authenticity
        self.get_disputed_offers = get_disputed_offers
        self.public_verify_offer = public_verify_offer

    # ── generic SQL helper ────────────────────────────────────────────
    def q(self, sql: str) -> pd.DataFrame:
        return _cached_query(self.DB, sql)

    # ── one cached loader per task engine ─────────────────────────────
    def get_metrics(self):          # Task 5 — Liquidity
        return _cached_liquidity(self.DB)

    def get_revenue(self):          # Task 6 — Revenue
        return _cached_revenue(self.DB)

    def get_conversion(self):       # Task 7 — Conversion
        return _cached_conversion(self.DB)

    def get_refund_metrics(self):   # Task 8 — Refunds
        return _cached_refunds(self.DB)

    def get_arpu(self):             # Task 9 — ARPU & Cohorts
        return _cached_arpu(self.DB)

    def get_rcc(self):              # Task 10 — Revenue Command Center
        return _cached_rcc(self.DB)

    def get_rcc_checks(self):
        return _cached_rcc_checks(self.DB)

    def get_offer(self):            # Task 11 — Offer Funnel & E-Sign
        return _cached_offer(self.DB)

    def get_offer_checks(self):
        return _cached_offer_checks(self.DB)

    def get_tth(self):              # Task 12 — Time-to-Hire
        return _cached_tth(self.DB)

    def get_acceptance(self):       # Task 13 — Offer→Acceptance
        return _cached_acceptance(self.DB)

    def get_acceptance_checks(self):
        return _cached_acceptance_checks(self.DB)


# ── module-level cached functions (st.cache_data needs free functions) ──
@st.cache_data(ttl=30)
def _cached_query(db_path, sql):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df

@st.cache_data(ttl=30)
def _cached_liquidity(db_path):
    return _compute_liquidity(db_path)

@st.cache_data(ttl=30)
def _cached_revenue(db_path):
    return _compute_revenue(db_path)

@st.cache_data(ttl=30)
def _cached_conversion(db_path):
    return _compute_conversion(db_path)

@st.cache_data(ttl=30)
def _cached_refunds(db_path):
    return _compute_refunds(db_path)

@st.cache_data(ttl=30)
def _cached_arpu(db_path):
    return _compute_arpu(db_path)

@st.cache_data(ttl=30)
def _cached_rcc(db_path):
    return _compute_rcc(db_path)

@st.cache_data(ttl=30)
def _cached_rcc_checks(db_path):
    return _validate_rcc(db_path)

@st.cache_data(ttl=30)
def _cached_offer(db_path):
    return _compute_offer(db_path)

@st.cache_data(ttl=30)
def _cached_offer_checks(db_path):
    return _validate_offer(db_path)

@st.cache_data(ttl=30)
def _cached_tth(db_path):
    return _compute_tth(db_path)

@st.cache_data(ttl=30)
def _cached_acceptance(db_path):
    return _compute_acceptance(db_path)

@st.cache_data(ttl=30)
def _cached_acceptance_checks(db_path):
    return _validate_acceptance(db_path)
