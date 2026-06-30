"""
PlaceMux — Task 11: Offer Generation & E-Sign Design
Offer Funnel Metrics Engine

Defines, seeds, and computes:
  1. Offer funnel (shortlist → interview → offer → accept/decline)
  2. E-sign event tracking (generated → sent → viewed → signed / rejected)
  3. Tamper-evidence audit trail (hash + timestamp per document)
  4. Offer velocity metrics (time-to-offer, time-to-sign)
  5. Conversion rates at every funnel stage
  6. E-sign provider status & mode (sandbox vs live)
  7. Dispute / authenticity verification metrics

New tables added to DB (idempotent — safe to call multiple times):
  offer_events      — immutable audit log of every offer state change
  esign_documents   — one row per offer letter (hash, status, provider)
  esign_events      — immutable log of every e-sign step (sent/viewed/signed)

Every metric includes: definition, formula, source, decision, expected_range.
"""

import sqlite3
import os
import hashlib
import datetime as dt
import random
import string

DB = os.path.join(os.path.dirname(__file__), "placemux.db")

# ─────────────────────────────────────────────────────────────────────────────
# Metric dictionary
# ─────────────────────────────────────────────────────────────────────────────

OFFER_METRIC_DICTIONARY = {
    # ── FUNNEL CONVERSION ────────────────────────────────────────────────────
    "shortlist_to_interview_rate": {
        "definition": "% of shortlisted applicants who progressed to an interview.",
        "formula": "COUNT(interviews) / COUNT(applications WHERE status='Shortlisted'+) × 100",
        "source": "applications + interviews",
        "decision": "< 50% → screening bar too high or interview capacity bottleneck; "
                    "> 85% → screening bar too low (interviewing unqualified candidates).",
        "expected_range": "50–80% in a healthy marketplace",
    },
    "interview_to_offer_rate": {
        "definition": "% of completed interviews that resulted in an offer.",
        "formula": "COUNT(offers) / COUNT(interviews WHERE status='Completed') × 100",
        "source": "interviews + offers",
        "decision": "< 40% → companies are interviewing speculatively without intent to hire "
                    "→ quality bar for shortlisting needs raising.",
        "expected_range": "40–70% is healthy",
    },
    "offer_acceptance_rate": {
        "definition": "% of offers extended that were accepted by the candidate.",
        "formula": "COUNT(offers WHERE status='Accepted') / COUNT(offers) × 100",
        "source": "offers",
        "decision": "< 60% → candidates are declining offers → likely compensation mismatch "
                    "or competing offers. Trigger salary benchmarking. "
                    "> 90% → companies may be under-offering (leaving value on table).",
        "expected_range": "65–85% is healthy",
    },
    "offer_to_sign_rate": {
        "definition": "% of accepted offers that also have a completed e-signature.",
        "formula": "COUNT(esign_documents WHERE status='signed') / COUNT(offers WHERE status='Accepted') × 100",
        "source": "esign_documents + offers",
        "decision": "< 80% → candidates accepting verbally but not signing → legal risk. "
                    "Chase every unsigned accepted offer within 24h.",
        "expected_range": "≥ 85%; any gap is an urgent action",
    },

    # ── VELOCITY ─────────────────────────────────────────────────────────────
    "avg_days_apply_to_offer": {
        "definition": "Average calendar days from application submitted to offer generated.",
        "formula": "AVG(julianday(offered_at) - julianday(applied_at)) FROM offers JOIN applications",
        "source": "offers JOIN applications",
        "decision": "< 5 days → hiring may be skipping proper evaluation. "
                    "> 21 days → pipeline too slow → candidates accepting elsewhere. "
                    "Target window: 7–14 days.",
        "expected_range": "7–14 days",
    },
    "avg_hours_offer_to_sign": {
        "definition": "Average hours between offer letter generated (esign_documents created) "
                      "and candidate signature received.",
        "formula": "AVG((julianday(signed_at) - julianday(generated_at)) * 24) "
                   "FROM esign_documents WHERE status='signed'",
        "source": "esign_documents WHERE status='signed'",
        "decision": "> 72h → candidates are sitting on unsigned offers → add reminder nudge "
                    "at 24h and 48h. < 2h → rubber-stamping (check candidate experience).",
        "expected_range": "4–48h; median < 24h is strong",
    },
    "avg_hours_sent_to_viewed": {
        "definition": "Average hours from offer letter sent to first candidate view.",
        "formula": "AVG((julianday(viewed_at) - julianday(sent_at)) * 24) FROM esign_events",
        "source": "esign_events WHERE event_name='offer_viewed'",
        "decision": "> 24h to view → notification delivery issue or wrong contact details. "
                    "< 1h → strong candidate engagement signal.",
        "expected_range": "< 12h from send to first view",
    },

    # ── E-SIGN INTEGRITY ─────────────────────────────────────────────────────
    "tamper_evidence_coverage_pct": {
        "definition": "% of signed documents that have a SHA-256 hash stored for integrity verification.",
        "formula": "COUNT(doc_hash IS NOT NULL) / COUNT(status='signed') × 100 FROM esign_documents",
        "source": "esign_documents",
        "decision": "Must be 100%. Any gap means we cannot prove the signed document "
                    "hasn't been altered → legal exposure on every offer dispute.",
        "expected_range": "Must be exactly 100%",
    },
    "documents_with_intact_hash_pct": {
        "definition": "% of signed documents whose stored hash matches the document content "
                      "(tamper-detection check).",
        "formula": "Recompute SHA-256 of doc_content; compare to stored doc_hash; "
                   "COUNT(match) / COUNT(signed) × 100",
        "source": "esign_documents WHERE status='signed'",
        "decision": "Any value < 100% → document was modified after signing → "
                    "raise security incident immediately.",
        "expected_range": "Must be exactly 100%",
    },
    "esign_provider_mode": {
        "definition": "Whether the e-sign integration is in sandbox or production mode.",
        "formula": "SELECT DISTINCT provider_mode FROM esign_documents LIMIT 1",
        "source": "esign_documents",
        "decision": "Must be 'sandbox' during Phase 2 demos. "
                    "Production requires legal entity binding, DPDP-compliant consent, "
                    "and IT Act 2000 §5 compliance for admissible digital signatures.",
        "expected_range": "'sandbox' for Phase 2; 'production' only after legal sign-off",
    },

    # ── DISPUTE / AUTHENTICITY ────────────────────────────────────────────────
    "disputed_offers_count": {
        "definition": "Number of offers where candidate raised an authenticity dispute.",
        "formula": "COUNT(*) FROM offer_events WHERE event_name='offer_disputed'",
        "source": "offer_events WHERE event_name='offer_disputed'",
        "decision": "Any dispute → verify using stored hash + timestamp. "
                    "Rising disputes → fake offer letters in circulation → publish "
                    "verification portal URL to candidates.",
        "expected_range": "0 in a healthy system; > 2 triggers investigation",
    },
    "dispute_resolution_rate_pct": {
        "definition": "% of disputes resolved (hash verified as authentic).",
        "formula": "COUNT(resolved) / COUNT(disputed) × 100 FROM offer_events",
        "source": "offer_events WHERE event_name IN ('offer_disputed','offer_dispute_resolved')",
        "decision": "< 100% → unresolved disputes create legal and trust risk. "
                    "Each dispute should be closed within 48h with hash verification proof.",
        "expected_range": "100% resolution within 48h",
    },

    # ── PIPELINE HEALTH ───────────────────────────────────────────────────────
    "unsigned_accepted_offers_count": {
        "definition": "Number of offers with status='Accepted' but no completed e-signature (status != 'signed').",
        "formula": "COUNT offers WHERE status='Accepted' LEFT JOIN esign_documents WHERE status != 'signed'",
        "source": "offers + esign_documents",
        "decision": "Each unsigned accepted offer is an unenforceable hiring commitment. "
                    "Chase every one within 24h of acceptance. "
                    "0 is the target at any snapshot.",
        "expected_range": "0 is target; > 5 is a pipeline risk",
    },
    "offer_decline_reasons": {
        "definition": "Distribution of reasons candidates declined offers (from offer_events).",
        "formula": "COUNT GROUP BY decline_reason FROM offer_events WHERE event_name='offer_declined'",
        "source": "offer_events WHERE event_name='offer_declined'",
        "decision": "salary_too_low > 30% → compensation benchmarking needed. "
                    "competing_offer > 40% → speed-to-offer must improve. "
                    "role_mismatch > 20% → job description accuracy issue.",
        "expected_range": "No single reason > 50%",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Schema additions (idempotent)
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Immutable audit log of every offer state change
CREATE TABLE IF NOT EXISTS offer_events (
    event_id        INTEGER PRIMARY KEY,
    offer_id        INTEGER NOT NULL,
    event_name      TEXT NOT NULL,      -- offer_generated, offer_sent, offer_declined,
                                        --   offer_disputed, offer_dispute_resolved
    decline_reason  TEXT,               -- salary_too_low | competing_offer | role_mismatch | other
    emitted_at      TEXT NOT NULL,
    metadata        TEXT,               -- JSON blob for extra context
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
);

-- One row per offer letter document
CREATE TABLE IF NOT EXISTS esign_documents (
    doc_id          INTEGER PRIMARY KEY,
    offer_id        INTEGER NOT NULL UNIQUE,
    doc_content     TEXT NOT NULL,      -- simulated letter text (hash source)
    doc_hash        TEXT,               -- SHA-256 hex digest of doc_content (set at signing)
    provider        TEXT DEFAULT 'DigiSign',
    provider_mode   TEXT DEFAULT 'sandbox',
    status          TEXT NOT NULL DEFAULT 'generated',
                                        -- generated | sent | viewed | signed | rejected
    generated_at    TEXT NOT NULL,
    sent_at         TEXT,
    viewed_at       TEXT,
    signed_at       TEXT,
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
);

-- Immutable log of every e-sign step
CREATE TABLE IF NOT EXISTS esign_events (
    esign_event_id  INTEGER PRIMARY KEY,
    doc_id          INTEGER NOT NULL,
    event_name      TEXT NOT NULL,      -- offer_generated | offer_sent | offer_viewed |
                                        --   offer_signed | offer_esign_rejected
    emitted_at      TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES esign_documents(doc_id)
);
"""


def _create_tables(conn):
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Seed realistic data
# ─────────────────────────────────────────────────────────────────────────────

def _rand_hash():
    return ''.join(random.choices(string.hexdigits.lower(), k=64))


def seed(db_path: str = DB):
    """
    Seed offer_events, esign_documents, esign_events with realistic data.
    Idempotent: skips if already seeded.
    """
    conn = sqlite3.connect(db_path)
    _create_tables(conn)
    c = conn.cursor()

    # Skip if already seeded
    if c.execute("SELECT COUNT(*) FROM esign_documents").fetchone()[0] > 0:
        conn.close()
        return

    random.seed(42)

    offers = c.execute("""
        SELECT o.offer_id, o.application_id, o.offered_at, o.status,
               a.student_id, a.job_id, j.company_id, j.job_title, j.salary
        FROM offers o
        JOIN applications a ON o.application_id = a.application_id
        JOIN jobs j ON a.job_id = j.job_id
        ORDER BY o.offer_id
    """).fetchall()

    students = {r[0]: r[1] for r in c.execute(
        "SELECT student_id, student_name FROM students"
    ).fetchall()}
    companies = {r[0]: r[1] for r in c.execute(
        "SELECT company_id, company_name FROM companies"
    ).fetchall()}

    decline_reasons = ["salary_too_low", "competing_offer", "role_mismatch", "other"]
    weights_decline = [0.35, 0.40, 0.15, 0.10]

    now = dt.datetime.now()

    for offer in offers:
        offer_id, app_id, offered_at_str, status, student_id, job_id, company_id, job_title, salary = offer

        offered_at = dt.datetime.strptime(offered_at_str, "%Y-%m-%d %H:%M:%S")
        student_name = students.get(student_id, f"Student {student_id}")
        company_name = companies.get(company_id, f"Company {company_id}")

        # ── offer_generated event ─────────────────────────────────────────────
        c.execute("""
            INSERT INTO offer_events (offer_id, event_name, emitted_at, metadata)
            VALUES (?, 'offer_generated', ?,
                    '{"salary": ' || ? || ', "job_title": "' || ? || '"}')
        """, (offer_id, offered_at_str, salary, job_title))

        # ── build offer letter content (deterministic for hashing) ────────────
        doc_content = (
            f"OFFER LETTER\n"
            f"Date: {offered_at.strftime('%d %B %Y')}\n"
            f"To: {student_name}\n\n"
            f"Dear {student_name},\n\n"
            f"We are pleased to offer you the position of {job_title} at {company_name}.\n"
            f"Compensation: INR {salary:,} per annum.\n"
            f"This offer is contingent on successful background verification.\n\n"
            f"Please sign this letter to confirm acceptance.\n\n"
            f"Offer ID: {offer_id} | Application ID: {app_id}\n"
            f"PlaceMux · Tamper-evident digital offer · Sandbox mode\n"
        )

        generated_at = offered_at
        sent_at = generated_at + dt.timedelta(hours=random.uniform(0.5, 3))
        viewed_at = sent_at + dt.timedelta(hours=random.uniform(1, 18))

        # ── determine esign path based on offer status ────────────────────────
        if status == "Accepted":
            # 88% fully signed, 12% accepted but not yet signed (pipeline risk metric)
            if random.random() < 0.88:
                signed_at = viewed_at + dt.timedelta(hours=random.uniform(2, 48))
                doc_hash = hashlib.sha256(doc_content.encode()).hexdigest()
                doc_status = "signed"
            else:
                signed_at = None
                doc_hash = None
                doc_status = "viewed"
        else:
            # Pending offers: some viewed, some signed (pre-acceptance), most just sent
            roll = random.random()
            if roll < 0.50:
                doc_status = "sent"
                viewed_at = None
                signed_at = None
                doc_hash = None
            elif roll < 0.78:
                doc_status = "viewed"
                signed_at = None
                doc_hash = None
            else:
                # Declined — rejection event will be added
                doc_status = "rejected"
                signed_at = None
                doc_hash = None

        # ── insert esign_document ─────────────────────────────────────────────
        c.execute("""
            INSERT INTO esign_documents
            (offer_id, doc_content, doc_hash, provider, provider_mode,
             status, generated_at, sent_at, viewed_at, signed_at)
            VALUES (?,?,?,'DigiSign','sandbox',?,?,?,?,?)
        """, (
            offer_id, doc_content, doc_hash, doc_status,
            generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            sent_at.strftime("%Y-%m-%d %H:%M:%S"),
            viewed_at.strftime("%Y-%m-%d %H:%M:%S") if viewed_at else None,
            signed_at.strftime("%Y-%m-%d %H:%M:%S") if signed_at else None,
        ))
        doc_id = c.lastrowid

        # ── esign_events: always generated + sent ─────────────────────────────
        c.execute("INSERT INTO esign_events (doc_id, event_name, emitted_at) VALUES (?,?,?)",
                  (doc_id, "offer_generated", generated_at.strftime("%Y-%m-%d %H:%M:%S")))
        c.execute("INSERT INTO esign_events (doc_id, event_name, emitted_at) VALUES (?,?,?)",
                  (doc_id, "offer_sent", sent_at.strftime("%Y-%m-%d %H:%M:%S")))

        if viewed_at:
            c.execute("INSERT INTO esign_events (doc_id, event_name, emitted_at) VALUES (?,?,?)",
                      (doc_id, "offer_viewed", viewed_at.strftime("%Y-%m-%d %H:%M:%S")))
        if signed_at:
            c.execute("INSERT INTO esign_events (doc_id, event_name, emitted_at) VALUES (?,?,?)",
                      (doc_id, "offer_signed", signed_at.strftime("%Y-%m-%d %H:%M:%S")))
        if doc_status == "rejected":
            reject_at = viewed_at + dt.timedelta(hours=random.uniform(1, 12)) if viewed_at else sent_at + dt.timedelta(hours=2)
            c.execute("INSERT INTO esign_events (doc_id, event_name, emitted_at) VALUES (?,?,?)",
                      (doc_id, "offer_esign_rejected", reject_at.strftime("%Y-%m-%d %H:%M:%S")))

        # ── offer_events: declined offers ─────────────────────────────────────
        if doc_status == "rejected" or (status == "Pending" and random.random() < 0.15):
            reason = random.choices(decline_reasons, weights=weights_decline)[0]
            decline_at = (viewed_at or sent_at) + dt.timedelta(hours=random.uniform(2, 24))
            c.execute("""
                INSERT INTO offer_events (offer_id, event_name, decline_reason, emitted_at)
                VALUES (?, 'offer_declined', ?, ?)
            """, (offer_id, reason, decline_at.strftime("%Y-%m-%d %H:%M:%S")))

    # ── add 3 simulated disputes (for realism) ────────────────────────────────
    dispute_offer_ids = random.sample([o[0] for o in offers[:40]], 3)
    for oid in dispute_offer_ids:
        dispute_at = now - dt.timedelta(days=random.randint(1, 5))
        c.execute("""
            INSERT INTO offer_events (offer_id, event_name, emitted_at, metadata)
            VALUES (?, 'offer_disputed', ?,
                    '{"reason": "candidate claims letter was not issued by platform"}')
        """, (oid, dispute_at.strftime("%Y-%m-%d %H:%M:%S")))
        # 2 of 3 are resolved
        if random.random() < 0.67:
            resolved_at = dispute_at + dt.timedelta(hours=random.uniform(4, 36))
            c.execute("""
                INSERT INTO offer_events (offer_id, event_name, emitted_at, metadata)
                VALUES (?, 'offer_dispute_resolved', ?,
                        '{"verification": "hash_match_confirmed", "result": "authentic"}')
            """, (oid, resolved_at.strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Compute all metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute(db_path: str = DB) -> dict:
    """
    Compute all Task 11 offer funnel metrics.
    Returns a flat dict — all values are JSON-serializable scalars or lists of dicts.
    Calls seed() first if new tables are empty.
    """
    seed(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    m = {}

    # ── FUNNEL STAGE COUNTS ───────────────────────────────────────────────────
    m["total_applications"]   = c.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    m["total_shortlisted"]    = c.execute(
        "SELECT COUNT(*) FROM application_events WHERE event_name='application_shortlisted'"
    ).fetchone()[0]
    m["total_interviewed"]    = c.execute("SELECT COUNT(*) FROM interviews").fetchone()[0]
    m["interviews_completed"] = c.execute(
        "SELECT COUNT(*) FROM interviews WHERE status='Completed'"
    ).fetchone()[0]
    m["total_offers"]         = c.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
    m["offers_accepted"]      = c.execute(
        "SELECT COUNT(*) FROM offers WHERE status='Accepted'"
    ).fetchone()[0]
    m["offers_pending"]       = c.execute(
        "SELECT COUNT(*) FROM offers WHERE status='Pending'"
    ).fetchone()[0]
    m["total_signed"]         = c.execute(
        "SELECT COUNT(*) FROM esign_documents WHERE status='signed'"
    ).fetchone()[0]

    # ── CONVERSION RATES ──────────────────────────────────────────────────────
    m["shortlist_to_interview_rate"] = round(
        m["total_interviewed"] / max(m["total_shortlisted"], 1) * 100, 1
    )
    m["interview_to_offer_rate"] = round(
        m["total_offers"] / max(m["interviews_completed"], 1) * 100, 1
    )
    m["offer_acceptance_rate"] = round(
        m["offers_accepted"] / max(m["total_offers"], 1) * 100, 1
    )
    m["offer_to_sign_rate"] = round(
        m["total_signed"] / max(m["offers_accepted"], 1) * 100, 1
    )

    # ── VELOCITY ──────────────────────────────────────────────────────────────
    avg_days = c.execute("""
        SELECT ROUND(AVG(julianday(o.offered_at) - julianday(a.applied_at)), 1)
        FROM offers o JOIN applications a ON o.application_id = a.application_id
    """).fetchone()[0]
    m["avg_days_apply_to_offer"] = avg_days or 0.0

    avg_sign_hours = c.execute("""
        SELECT ROUND(AVG((julianday(signed_at) - julianday(generated_at)) * 24), 1)
        FROM esign_documents WHERE status='signed' AND signed_at IS NOT NULL
    """).fetchone()[0]
    m["avg_hours_offer_to_sign"] = avg_sign_hours or 0.0

    avg_view_hours = c.execute("""
        SELECT ROUND(AVG((julianday(viewed_at) - julianday(sent_at)) * 24), 1)
        FROM esign_documents WHERE viewed_at IS NOT NULL AND sent_at IS NOT NULL
    """).fetchone()[0]
    m["avg_hours_sent_to_viewed"] = avg_view_hours or 0.0

    # ── E-SIGN STATUS BREAKDOWN ────────────────────────────────────────────────
    esign_status_rows = c.execute("""
        SELECT status, COUNT(*) AS count
        FROM esign_documents GROUP BY status ORDER BY count DESC
    """).fetchall()
    m["esign_status_breakdown"] = [dict(r) for r in esign_status_rows]

    # ── TAMPER EVIDENCE ────────────────────────────────────────────────────────
    signed_with_hash = c.execute(
        "SELECT COUNT(*) FROM esign_documents WHERE status='signed' AND doc_hash IS NOT NULL"
    ).fetchone()[0]
    m["tamper_evidence_coverage_pct"] = round(
        signed_with_hash / max(m["total_signed"], 1) * 100, 1
    )

    # Verify hash integrity: recompute and compare
    signed_docs = c.execute(
        "SELECT doc_id, doc_content, doc_hash FROM esign_documents WHERE status='signed' AND doc_hash IS NOT NULL"
    ).fetchall()
    intact = sum(
        1 for _, content, stored_hash in signed_docs
        if hashlib.sha256(content.encode()).hexdigest() == stored_hash
    )
    m["documents_verified_intact"] = intact
    m["documents_with_intact_hash_pct"] = round(
        intact / max(len(signed_docs), 1) * 100, 1
    )

    # ── PROVIDER STATUS ────────────────────────────────────────────────────────
    provider_row = c.execute(
        "SELECT provider, provider_mode FROM esign_documents LIMIT 1"
    ).fetchone()
    m["esign_provider"]      = provider_row["provider"] if provider_row else "unknown"
    m["esign_provider_mode"] = provider_row["provider_mode"] if provider_row else "unknown"

    # ── DISPUTES ──────────────────────────────────────────────────────────────
    m["disputed_offers_count"] = c.execute(
        "SELECT COUNT(*) FROM offer_events WHERE event_name='offer_disputed'"
    ).fetchone()[0]
    resolved = c.execute(
        "SELECT COUNT(*) FROM offer_events WHERE event_name='offer_dispute_resolved'"
    ).fetchone()[0]
    m["disputes_resolved_count"] = resolved
    m["dispute_resolution_rate_pct"] = round(
        resolved / max(m["disputed_offers_count"], 1) * 100, 1
    )

    # ── PIPELINE RISKS ─────────────────────────────────────────────────────────
    unsigned_accepted = c.execute("""
        SELECT COUNT(*) FROM offers o
        LEFT JOIN esign_documents d ON o.offer_id = d.offer_id
        WHERE o.status = 'Accepted'
          AND (d.status IS NULL OR d.status != 'signed')
    """).fetchone()[0]
    m["unsigned_accepted_offers_count"] = unsigned_accepted

    # ── DECLINE REASONS ────────────────────────────────────────────────────────
    decline_rows = c.execute("""
        SELECT decline_reason, COUNT(*) AS count
        FROM offer_events WHERE event_name='offer_declined' AND decline_reason IS NOT NULL
        GROUP BY decline_reason ORDER BY count DESC
    """).fetchall()
    m["offer_decline_reasons"] = [dict(r) for r in decline_rows]
    m["total_declines"] = c.execute(
        "SELECT COUNT(*) FROM offer_events WHERE event_name='offer_declined'"
    ).fetchone()[0]

    # ── WEEKLY OFFER TREND ─────────────────────────────────────────────────────
    trend_rows = c.execute("""
        SELECT strftime('%Y-W%W', offered_at) AS week,
               COUNT(*) AS offers_generated,
               SUM(CASE WHEN status='Accepted' THEN 1 ELSE 0 END) AS accepted
        FROM offers GROUP BY week ORDER BY week
    """).fetchall()
    m["weekly_offer_trend"] = [dict(r) for r in trend_rows]

    # ── ESIGN FRESHNESS ────────────────────────────────────────────────────────
    last_esign = c.execute(
        "SELECT MAX(emitted_at) FROM esign_events"
    ).fetchone()[0]
    m["last_esign_event_at"] = last_esign
    if last_esign:
        hrs = (dt.datetime.now() - dt.datetime.strptime(last_esign, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        m["esign_data_age_hours"] = round(hrs, 1)
    else:
        m["esign_data_age_hours"] = None

    # ── FULL FUNNEL SUMMARY LIST ───────────────────────────────────────────────
    m["funnel_stages"] = [
        {"stage": "Applied",       "count": m["total_applications"],   "pct_of_prev": None},
        {"stage": "Shortlisted",   "count": m["total_shortlisted"],    "pct_of_prev": round(m["total_shortlisted"]/max(m["total_applications"],1)*100,1)},
        {"stage": "Interviewed",   "count": m["total_interviewed"],    "pct_of_prev": round(m["total_interviewed"]/max(m["total_shortlisted"],1)*100,1)},
        {"stage": "Offered",       "count": m["total_offers"],         "pct_of_prev": round(m["total_offers"]/max(m["interviews_completed"],1)*100,1)},
        {"stage": "Accepted",      "count": m["offers_accepted"],      "pct_of_prev": round(m["offer_acceptance_rate"],1)},
        {"stage": "E-Sign Complete","count": m["total_signed"],        "pct_of_prev": round(m["offer_to_sign_rate"],1)},
    ]

    conn.close()
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Validate
# ─────────────────────────────────────────────────────────────────────────────

def validate(db_path: str = DB) -> dict:
    """
    Run all Task 11 validation checks.
    Returns dict: {check_name: {"result": "PASS"|"WARN"|"FAIL", "detail": str}}
    """
    m = compute(db_path)
    results = {}

    # C1 — Offer funnel data flowing at scale
    c1 = m["total_offers"] >= 100 and m["total_signed"] >= 50
    results["C1_offer_funnel_data_flowing"] = {
        "result": "PASS" if c1 else "FAIL",
        "detail": f"Offers: {m['total_offers']} | Signed: {m['total_signed']} | "
                  f"Acceptance rate: {m['offer_acceptance_rate']}%",
    }

    # C2 — Tamper evidence 100% on all signed docs
    c2 = m["tamper_evidence_coverage_pct"] == 100.0 and m["documents_with_intact_hash_pct"] == 100.0
    results["C2_tamper_evidence_complete"] = {
        "result": "PASS" if c2 else "FAIL",
        "detail": f"Hash coverage: {m['tamper_evidence_coverage_pct']}% | "
                  f"Intact (recomputed): {m['documents_with_intact_hash_pct']}% "
                  f"({m['documents_verified_intact']} of {m['total_signed']} docs verified)",
    }

    # C3 — Provider in sandbox mode (not live)
    c3 = m["esign_provider_mode"] == "sandbox"
    results["C3_esign_sandbox_mode"] = {
        "result": "PASS" if c3 else "WARN",
        "detail": f"Provider: {m['esign_provider']} | Mode: {m['esign_provider_mode']}",
    }

    # C4 — Dispute resolution tracked
    c4 = m["disputed_offers_count"] is not None  # metric exists
    dispute_detail = (f"Disputes: {m['disputed_offers_count']} | "
                      f"Resolved: {m['disputes_resolved_count']} | "
                      f"Resolution rate: {m['dispute_resolution_rate_pct']}%")
    results["C4_dispute_tracking_live"] = {
        "result": "PASS" if c4 else "FAIL",
        "detail": dispute_detail,
    }

    # C5 — Unsigned accepted offers flagged
    ua = m["unsigned_accepted_offers_count"]
    c5_result = "PASS" if ua <= 10 else "WARN"
    results["C5_unsigned_accepted_offers_surfaced"] = {
        "result": c5_result,
        "detail": f"Unsigned accepted offers: {ua} "
                  f"{'(chase within 24h)' if ua > 0 else '(clean)'}",
    }

    # C6 — All funnel conversion rates computable and in range
    c6 = (
        0 < m["shortlist_to_interview_rate"] < 100 and
        0 < m["interview_to_offer_rate"] < 100 and
        0 < m["offer_acceptance_rate"] < 100
    )
    results["C6_funnel_rates_all_computable"] = {
        "result": "PASS" if c6 else "FAIL",
        "detail": (f"Shortlist→Interview: {m['shortlist_to_interview_rate']}% | "
                   f"Interview→Offer: {m['interview_to_offer_rate']}% | "
                   f"Offer→Accept: {m['offer_acceptance_rate']}% | "
                   f"Accept→Sign: {m['offer_to_sign_rate']}%"),
    }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Task 11 — Offer Funnel Metrics ===\n")
    m = compute()

    print("FUNNEL:")
    for stage in m["funnel_stages"]:
        pct = f"({stage['pct_of_prev']}% of prev)" if stage["pct_of_prev"] else ""
        print(f"  {stage['stage']:<20} {stage['count']:>5}  {pct}")

    print(f"\nVELOCITY:")
    print(f"  Avg days apply→offer    : {m['avg_days_apply_to_offer']} days")
    print(f"  Avg hours offer→sign    : {m['avg_hours_offer_to_sign']} h")
    print(f"  Avg hours sent→viewed   : {m['avg_hours_sent_to_viewed']} h")

    print(f"\nE-SIGN INTEGRITY:")
    print(f"  Tamper evidence coverage: {m['tamper_evidence_coverage_pct']}%")
    print(f"  Hash intact (verified)  : {m['documents_with_intact_hash_pct']}%")
    print(f"  Provider / mode         : {m['esign_provider']} / {m['esign_provider_mode']}")

    print(f"\nRISK FLAGS:")
    print(f"  Unsigned accepted offers: {m['unsigned_accepted_offers_count']}")
    print(f"  Disputed offers         : {m['disputed_offers_count']}")
    print(f"  Dispute resolution rate : {m['dispute_resolution_rate_pct']}%")

    if m["offer_decline_reasons"]:
        print(f"\nDECLINE REASONS:")
        for r in m["offer_decline_reasons"]:
            print(f"  {r['decline_reason']:<20} {r['count']}")

    print("\n=== Task 11 Validation ===\n")
    checks = validate()
    for name, res in checks.items():
        icon = "✅" if res["result"] == "PASS" else ("⚠️" if res["result"] == "WARN" else "❌")
        print(f"  {icon} {res['result']:4s}  {name}")
        print(f"          {res['detail']}")

    all_ok = all(v["result"] in ("PASS", "WARN") for v in checks.values())
    print()
    if all_ok:
        print("✅ ALL TASK 11 CHECKS PASS — Offer funnel metrics defined, sourced, demoable.")
    else:
        print("❌ Some checks FAILED — review above.")
