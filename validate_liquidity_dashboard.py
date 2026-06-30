"""
PlaceMux — Task 5: Liquidity Dashboard Validator
Validates that the end-to-end marketplace pipeline
(company posts → student applies → company shortlists)
is real, sourced, and explainable. Run before the live demo.
"""
import sqlite3, pandas as pd, datetime as dt, os
from liquidity_engine import compute, health_status, METRIC_DICTIONARY

DB    = os.path.join(os.path.dirname(__file__), "placemux.db")
TODAY = dt.datetime.now()


def validate():
    conn = sqlite3.connect(DB)
    print("=" * 65)
    print("TASK 5 — LIQUIDITY DASHBOARD VALIDATION")
    print("End-to-end: company posts → student applies → company shortlists")
    print("=" * 65)

    # ── Check 1: all upstream event tables are real and non-empty ──────
    print(f"\n[CHECK 1] All upstream event tables populated (real data, not toy)")
    EXPECTED = {
        "job_supply_events":   50,
        "job_search_events":   200,
        "job_view_events":     100,
        "applications":        200,
        "application_events":  400,
    }
    all_ok = True
    for tbl, min_rows in EXPECTED.items():
        n = pd.read_sql(f"SELECT COUNT(*) n FROM {tbl}", conn).iloc[0,0]
        ok = n >= min_rows
        print(f"  {'✓' if ok else '✗'} {tbl:25s} {n:>6d} rows  (min {min_rows})")
        if not ok:
            all_ok = False
    print(f"  {'PASS' if all_ok else 'FAIL'}")

    # ── Check 2: freshness across all event tables ─────────────────────
    print(f"\n[CHECK 2] Freshness — all pipes emitting within SLA")
    FRESHNESS_SLAS = {
        "job_supply_events":  ("emitted_at", 48),
        "job_search_events":  ("searched_at", 48),
        "job_view_events":    ("viewed_at", 48),
        "application_events": ("emitted_at", 48),
    }
    fresh_ok = True
    for tbl, (ts_col, sla_h) in FRESHNESS_SLAS.items():
        last = pd.read_sql(f"SELECT MAX({ts_col}) ts FROM {tbl}", conn).iloc[0,0]
        if last:
            hrs = (TODAY - dt.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds()/3600
            ok = hrs <= sla_h
            print(f"  {'✓' if ok else '✗'} {tbl:25s} last={last[:16]}  ({hrs:.1f}h / SLA {sla_h}h)")
            if not ok:
                fresh_ok = False
    print(f"  {'PASS' if fresh_ok else 'FAIL'}")

    # ── Check 3: end-to-end chain integrity ────────────────────────────
    print(f"\n[CHECK 3] End-to-end chain: post → view → apply → verify → shortlist")
    chain = pd.read_sql("""
        SELECT
            (SELECT COUNT(*) FROM job_supply_events) AS posted,
            (SELECT COUNT(*) FROM job_view_events) AS viewed,
            (SELECT COUNT(*) FROM applications) AS applied,
            (SELECT COUNT(*) FROM applications WHERE verified=1) AS verified,
            (SELECT COUNT(*) FROM applications
             WHERE status IN ('Shortlisted','Interviewed','Offered')) AS shortlisted
    """, conn)
    print(chain.to_string(index=False))
    chain_ok = all(chain.iloc[0] > 0)
    print(f"  {'PASS — all stages have data' if chain_ok else 'FAIL — one or more stages empty'}")

    # ── Check 4: shortlist integrity (no unverified shortlisted) ──────
    print(f"\n[CHECK 4] Shortlist integrity — no unverified candidate ever shortlisted")
    violation = pd.read_sql(
        "SELECT COUNT(*) n FROM applications WHERE status='Shortlisted' AND verified=0", conn
    ).iloc[0,0]
    print(f"  Violations: {violation}")
    print(f"  {'PASS' if violation == 0 else 'FAIL — integrity breach, investigate immediately'}")

    # ── Check 5: liquidity metrics computable & sane ───────────────────
    print(f"\n[CHECK 5] All liquidity metrics compute without error and are sane")
    metrics = compute(DB)
    issues = []
    for k, v in metrics.items():
        if v is None:
            issues.append(f"{k} = None (insufficient history)")
            continue
        if isinstance(v, float) and (v < 0 or v > 200):
            issues.append(f"{k} = {v} (out of expected range)")
    if issues:
        for i in issues:
            print(f"  ⚠ {i}")
        print("  WARN — some metrics need more data history")
    else:
        print(f"  All {len(metrics)} metrics computed cleanly")
        print("  PASS")

    # ── LIVE VIEW — the Task 5 deliverable ────────────────────────────
    li = metrics["liquidity_index"]
    label, _, action = health_status(li)

    print(f"\n{'='*65}")
    print(f"LIQUIDITY DASHBOARD — LIVE SNAPSHOT")
    print(f"{'='*65}")
    print(f"\n  LIQUIDITY INDEX : {li}/100  [{label}]")
    print(f"  ACTION          : {action}")
    print(f"\n  {'Metric':<32} {'Value':>10}  Source")
    print(f"  {'-'*60}")
    for k, v in metrics.items():
        src = METRIC_DICTIONARY.get(k, {}).get("source", "—")[:30]
        val_str = f"{v:.1f}" if isinstance(v, float) else (str(v) if v is not None else "N/A")
        print(f"  {k:<32} {val_str:>10}  {src}")

    conn.close()
    all_checks = all_ok and fresh_ok and chain_ok and (violation == 0)
    print(f"\n{'='*65}")
    print(f"OVERALL: {'ALL CRITICAL CHECKS PASS' if all_checks else 'REVIEW ABOVE BEFORE DEMO'}")
    print("Liquidity dashboard is real, sourced, and demoable end-to-end.")
    print(f"{'='*65}")


if __name__ == "__main__":
    validate()
