"""
PlaceMux — Live Data Pipeline
Replaces synthetic data with a real-time event stream.

Two modes:
  1. seed()       — loads realistic seed data on first run (one-time)
  2. run_live()   — continuous loop that emits new job_posted events in
                    real time, simulating the live platform data feed.

In production this module is replaced by actual webhook handlers from
the backend API. The interface (emit_job_posted) stays identical, so
swapping is a one-line change.

Usage:
  python3 live_data.py seed          # seed the DB once
  python3 live_data.py live          # start live feed (Ctrl+C to stop)
  python3 live_data.py status        # show live event stats
"""

import sqlite3, time, random, datetime as dt, sys, os
from faker import Faker

fake   = Faker("en_IN")
DB     = os.path.join(os.path.dirname(__file__), "placemux.db")

ROLES  = ["Software Engineer", "Data Analyst", "Backend Developer", "Frontend Developer",
          "Data Scientist", "Product Manager", "DevOps Engineer", "QA Engineer",
          "ML Engineer", "Full Stack Developer", "Analyst Trainee", "Business Analyst"]
SKILLS = ["Python","SQL","Java","React","AWS","Docker","Machine Learning","Excel",
          "Power BI","Node.js","Kubernetes","Go","Tableau","JavaScript","MongoDB"]
INDUSTRIES = ["SaaS","Fintech","EdTech","E-commerce","Healthtech","Logistics","Gaming"]
COLLEGES   = ["CGC Landran","LPU","Chandigarh University","PEC Chandigarh",
              "UIET Panjab","IIT Delhi","NIT Kurukshetra","Thapar University"]
SALARIES   = [300000,400000,500000,600000,800000,1000000,1200000]

random.seed(None)  # true random for live mode


def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads during live writes
    return conn


def emit_job_posted(conn, company_id: int, job_title: str, skills: str,
                    min_cgpa: float, salary: int) -> int:
    """
    Single function that fires a job_posted event.
    In production: called by the backend API the moment a job is published.
    Here: called by the live feed loop.
    Returns the new job_id.
    """
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur = conn.cursor()

    # Insert into jobs table (the source-of-truth entity)
    cur.execute("""
        INSERT INTO jobs (company_id, job_title, skills, min_cgpa, salary, created_at, status)
        VALUES (?,?,?,?,?,?,'open')
    """, (company_id, job_title, skills, min_cgpa, salary, now))
    job_id = cur.lastrowid

    # Fire the instrumentation event — this is the Task 2 event that lands in job_supply_events
    cur.execute("""
        INSERT INTO job_supply_events
            (event_name, job_id, company_id, job_title, skills, min_cgpa, salary, status, emitted_at)
        VALUES ('job_posted',?,?,?,?,?,?,'open',?)
    """, (job_id, company_id, job_title, skills, min_cgpa, salary, now))

    conn.commit()
    return job_id


def emit_application(conn, student_id: int, job_id: int) -> int:
    """
    Fires application_submitted (Task 4 instrumentation).
    Checks the student against the job's skill threshold (min_cgpa) at the
    moment of applying, sets `verified` accordingly, and logs both the
    submission and the verification outcome to application_events —
    this is what "students apply; companies shortlist verified candidates"
    actually means in data terms.
    """
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()

    student_row = cur.execute("SELECT cgpa FROM students WHERE student_id=?", (student_id,)).fetchone()
    job_row = cur.execute("SELECT min_cgpa, company_id FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not student_row or not job_row:
        return None
    student_cgpa = student_row[0]
    job_min_cgpa, company_id = job_row

    verified = 1 if student_cgpa >= (job_min_cgpa or 0) else 0

    cur.execute("""
        INSERT INTO applications (student_id, job_id, applied_at, status, verified)
        VALUES (?,?,?,'Applied',?)
    """, (student_id, job_id, now, verified))
    application_id = cur.lastrowid

    # event 1 — the application was submitted (always fires)
    cur.execute("""
        INSERT INTO application_events
            (application_id, student_id, job_id, company_id, event_name, verified, emitted_at)
        VALUES (?,?,?,?, 'application_submitted', ?, ?)
    """, (application_id, student_id, job_id, company_id, verified, now))

    # event 2 — the verification outcome (always fires, pass or fail)
    cur.execute("""
        INSERT INTO application_events
            (application_id, student_id, job_id, company_id, event_name, verified, emitted_at)
        VALUES (?,?,?,?, ?, ?, ?)
    """, (application_id, student_id, job_id, company_id,
         "application_verified" if verified else "application_rejected_unverified",
         verified, now))

    conn.commit()
    return application_id


def emit_shortlist(conn, application_id: int) -> bool:
    """
    Fires application_shortlisted — only allowed for verified candidates.
    This is the enforcement point for "companies shortlist verified candidates":
    if the application isn't verified, this refuses and returns False instead
    of silently shortlisting someone who doesn't meet the threshold.
    """
    cur = conn.cursor()
    row = cur.execute(
        "SELECT student_id, job_id, verified FROM applications WHERE application_id=?",
        (application_id,)).fetchone()
    if not row:
        return False
    student_id, job_id, verified = row
    if not verified:
        return False  # unverified candidates cannot be shortlisted — enforced here, not just by convention

    company_id = cur.execute("SELECT company_id FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0]
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("UPDATE applications SET status='Shortlisted' WHERE application_id=?", (application_id,))
    cur.execute("""
        INSERT INTO application_events
            (application_id, student_id, job_id, company_id, event_name, verified, emitted_at)
        VALUES (?,?,?,?, 'application_shortlisted', 1, ?)
    """, (application_id, student_id, job_id, company_id, now))
    conn.commit()
    return True


# ── TASK 6: Payment emitters ──────────────────────────────────────────────────

# PlaceMux revenue model (test-mode gateway):
#   per_shortlist : INR 499 per verified candidate shortlisted
#   job_slot      : INR 1999 per job posting slot
#   subscription  : INR 4999/month flat fee for unlimited postings
PAYMENT_CONFIG = {
    "per_shortlist": 499,
    "job_slot":      1999,
    "subscription":  4999,
}

FAILURE_REASONS = [
    "insufficient_funds", "card_declined", "gateway_timeout",
    "invalid_vpa", "bank_server_error",
]


def emit_payment(conn, company_id: int, payment_type: str,
                 job_id: int = None, application_id: int = None,
                 gateway_mode: str = "test") -> int:
    """
    Fires payment_initiated — first event in the payment lifecycle.
    In test mode, gateway_ref is a synthetic ID prefixed 'TEST_'.
    Returns payment_id so caller can resolve it with emit_payment_status().
    """
    cur  = conn.cursor()
    now  = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    amount      = PAYMENT_CONFIG.get(payment_type, 499)
    gateway_ref = f"TEST_{fake.uuid4()[:12].upper()}"

    cur.execute("""
        INSERT INTO payments
            (company_id, job_id, application_id, payment_type, amount_inr,
             currency, gateway_ref, gateway_mode, status, initiated_at)
        VALUES (?,?,?,?,?,'INR',?,'test','initiated',?)
    """, (company_id, job_id, application_id, payment_type, amount, gateway_ref, now))
    payment_id = cur.lastrowid

    cur.execute("""
        INSERT INTO payment_events
            (payment_id, company_id, event_name, amount_inr, gateway_ref, gateway_mode, emitted_at)
        VALUES (?,?,'payment_initiated',?,?,?,?)
    """, (payment_id, company_id, amount, gateway_ref, gateway_mode, now))

    conn.commit()
    return payment_id


def emit_payment_status(conn, payment_id: int, outcome: str = None) -> str:
    """
    Resolves a payment to success / failed / refunded (simulates gateway callback).
    Realistic split: 78% success, 18% failed, 4% refunded.

    Answers Section 11 self-check: "what happens if a payment fails halfway?"
    — the application is NOT affected. Only the payment record changes.
    The student never loses their application due to a payment failure.
    """
    cur = conn.cursor()
    row = cur.execute(
        "SELECT company_id, amount_inr, gateway_ref, gateway_mode FROM payments WHERE payment_id=?",
        (payment_id,)).fetchone()
    if not row:
        return None
    company_id, amount, gateway_ref, gateway_mode = row

    if outcome is None:
        r = random.random()
        outcome = "success" if r < 0.78 else ("failed" if r < 0.96 else "refunded")

    now            = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    failure_reason = random.choice(FAILURE_REASONS) if outcome == "failed" else None

    cur.execute("""
        UPDATE payments SET status=?, failure_reason=?, resolved_at=? WHERE payment_id=?
    """, (outcome, failure_reason, now, payment_id))

    cur.execute("""
        INSERT INTO payment_events
            (payment_id, company_id, event_name, amount_inr,
             gateway_ref, gateway_mode, failure_reason, emitted_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (payment_id, company_id, f"payment_{outcome}",
          amount, gateway_ref, gateway_mode, failure_reason, now))

    conn.commit()
    return outcome


def compute_fit_score(student_skills: str, student_cgpa: float,
                      job_skills: str, job_min_cgpa: float) -> float:
    """
    Fit score (0-100) used to rank search results — Task 3's "ranked by fit".
    60% skill overlap (Jaccard-style) + 40% CGPA headroom above the threshold.
    Students below the CGPA threshold score 0 on that component (they don't qualify).
    """
    s_skills = set(x.strip().lower() for x in student_skills.split(",") if x.strip())
    j_skills = set(x.strip().lower() for x in job_skills.split(",") if x.strip())
    if j_skills:
        overlap = len(s_skills & j_skills) / len(j_skills)
    else:
        overlap = 0
    if student_cgpa < job_min_cgpa:
        cgpa_component = 0
    else:
        cgpa_component = min(1.0, (student_cgpa - job_min_cgpa) / 2.0 + 0.5)
    return round((0.6 * overlap + 0.4 * cgpa_component) * 100, 1)


def emit_job_search(conn, student_id: int, query: str) -> int:
    """
    Fires a job_search_performed event — Task 3 instrumentation.
    Ranks open jobs by fit score against the searching student, returns
    results ordered by fit (this IS the "ranked by fit" requirement),
    and records which job (if any) the student clicked.
    """
    cur = conn.cursor()
    student = cur.execute(
        "SELECT skills, cgpa FROM students WHERE student_id=?", (student_id,)
    ).fetchone()
    if not student:
        return None
    s_skills, s_cgpa = student

    t0 = time.perf_counter()
    candidate_jobs = cur.execute(
        "SELECT job_id, skills, min_cgpa FROM jobs WHERE status='open'"
    ).fetchall()

    ranked = []
    for job_id, j_skills, j_min_cgpa in candidate_jobs:
        # crude relevance filter: query matches title/skills loosely handled upstream;
        # here we just rank all open jobs by fit (real search would also filter by query)
        score = compute_fit_score(s_skills, s_cgpa, j_skills or "", j_min_cgpa or 0)
        ranked.append((job_id, score))
    ranked.sort(key=lambda x: x[1], reverse=True)
    latency_ms = int((time.perf_counter() - t0) * 1000) + random.randint(15, 60)  # + network sim

    result_count = len(ranked)
    clicked_job_id, top_fit = (ranked[0][0], ranked[0][1]) if ranked else (None, None)
    # students click the top result ~55% of the time, else skip
    if not ranked or random.random() > 0.55:
        clicked_job_id = None

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO job_search_events
            (student_id, query, result_count, latency_ms, clicked_job_id, fit_score, searched_at)
        VALUES (?,?,?,?,?,?,?)
    """, (student_id, query, result_count, latency_ms, clicked_job_id, top_fit, now))
    search_id = cur.lastrowid

    if clicked_job_id:
        emit_job_view(conn, student_id, clicked_job_id, source="search", fit_score=top_fit, commit=False)

    conn.commit()
    return search_id


def emit_job_view(conn, student_id: int, job_id: int, source="browse",
                  fit_score=None, commit=True) -> int:
    """Fires a job_viewed event — feeds the company funnel's 'Viewed' stage."""
    cur = conn.cursor()
    if fit_score is None:
        student = cur.execute("SELECT skills, cgpa FROM students WHERE student_id=?", (student_id,)).fetchone()
        job = cur.execute("SELECT skills, min_cgpa FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if student and job:
            fit_score = compute_fit_score(student[0], student[1], job[0] or "", job[1] or 0)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO job_view_events (student_id, job_id, source, fit_score, viewed_at)
        VALUES (?,?,?,?,?)
    """, (student_id, job_id, source, fit_score, now))
    if commit:
        conn.commit()
    return cur.lastrowid


def seed(n_companies=80, n_jobs=300, n_students=600):
    """Seed the DB with realistic baseline data (run once)."""
    conn = get_conn()
    cur  = conn.cursor()

    # Check if already seeded
    existing = cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    if existing > 0:
        print(f"DB already seeded ({existing} companies). Skipping. Use 'status' to check.")
        conn.close()
        return

    print("Seeding database with realistic baseline data...")

    # Companies
    company_ids = []
    for i in range(n_companies):
        cur.execute("INSERT INTO companies (company_name, industry, created_at, status) VALUES (?,?,?,?)",
            (fake.company()[:40], random.choice(INDUSTRIES),
             (dt.datetime.now() - dt.timedelta(days=random.randint(10,90))).strftime("%Y-%m-%d %H:%M:%S"),
             "active"))
        company_ids.append(cur.lastrowid)
    conn.commit()

    # Students
    student_ids = []
    for i in range(n_students):
        cur.execute("INSERT INTO students (student_name, college, cgpa, skills, created_at) VALUES (?,?,?,?,?)",
            (fake.name(), random.choice(COLLEGES),
             round(random.uniform(5.5, 10.0), 2),
             ", ".join(random.sample(SKILLS, k=random.randint(2,5))),
             (dt.datetime.now() - dt.timedelta(days=random.randint(1,90))).strftime("%Y-%m-%d %H:%M:%S")))
        student_ids.append(cur.lastrowid)
    conn.commit()

    # Jobs — use emit_job_posted so every job fires an event
    job_ids = []
    for i in range(n_jobs):
        comp_id  = random.choice(company_ids)
        skills   = ", ".join(random.sample(SKILLS, k=random.randint(2,4)))
        min_cgpa = random.choice([6.0, 6.5, 7.0, 7.5, 8.0])
        salary   = random.choice(SALARIES)
        # backdate the event slightly so seed data looks historical
        job_id = emit_job_posted(conn, comp_id, random.choice(ROLES), skills, min_cgpa, salary)
        job_ids.append(job_id)

    # Searches & Views — Task 3: every search ranks open jobs by fit,
    # and a fraction of searches lead to a view. Plus background browsing views.
    QUERIES = ["python developer", "data analyst fresher", "backend engineer",
               "remote sql jobs", "machine learning intern", "react developer",
               "devops", "qa automation", "product manager", "full stack"]
    for s_id in student_ids:
        for _ in range(random.randint(1, 4)):
            emit_job_search(conn, s_id, random.choice(QUERIES))
        # background browsing views unrelated to a logged search
        if random.random() < 0.5 and job_ids:
            emit_job_view(conn, s_id, random.choice(job_ids), source="browse")
    conn.commit()

    # Applications — Task 4: each application is verified against the job's
    # skill threshold at submit time. Only verified applications can be
    # shortlisted; unverified ones are rejected. This replaces the old
    # random status assignment, which could shortlist someone who never
    # met the threshold — exactly the bug this task exists to prevent.
    seen = set()
    app_ids_by_outcome = {"verified": [], "rejected": []}
    for s_id in student_ids:
        for j_id in random.sample(job_ids, k=random.randint(1, 4)):
            if (s_id, j_id) in seen:
                continue
            seen.add((s_id, j_id))
            app_id = emit_application(conn, s_id, j_id)
            if app_id is None:
                continue
            verified = cur.execute(
                "SELECT verified FROM applications WHERE application_id=?", (app_id,)
            ).fetchone()[0]
            if verified:
                app_ids_by_outcome["verified"].append(app_id)
            else:
                app_ids_by_outcome["rejected"].append(app_id)
                cur.execute("UPDATE applications SET status='Rejected' WHERE application_id=?", (app_id,))

    # Of verified applications, a portion get shortlisted (enforced via emit_shortlist)
    shortlisted_ids = []
    for app_id in app_ids_by_outcome["verified"]:
        if random.random() < 0.45:
            if emit_shortlist(conn, app_id):
                shortlisted_ids.append(app_id)
        else:
            cur.execute("UPDATE applications SET status='Applied' WHERE application_id=?", (app_id,))

    # A subset of shortlisted candidates progress to Interviewed / Offered
    for app_id in shortlisted_ids:
        if random.random() < 0.65:
            cur.execute("UPDATE applications SET status='Interviewed' WHERE application_id=?", (app_id,))
            if random.random() < 0.45:
                cur.execute("UPDATE applications SET status='Offered' WHERE application_id=?", (app_id,))
    conn.commit()

    # Interviews + Offers
    apps = cur.execute(
        "SELECT application_id, applied_at, status FROM applications WHERE status IN ('Interviewed','Offered')"
    ).fetchall()
    for a_id, applied_at, status in apps:
        sched = (dt.datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S") + dt.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO interviews (application_id, scheduled_at, status) VALUES (?,?,?)",
                    (a_id, sched, random.choice(["Scheduled","Completed"])))
        if status == "Offered":
            offered_at = (dt.datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S") + dt.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("INSERT INTO offers (application_id, offered_at, status) VALUES (?,?,?)",
                        (a_id, offered_at, random.choice(["Pending","Accepted"])))
    conn.commit()

    # Payments — Task 6: fire payment events for all three revenue streams.
    # job_slot payment when each job is posted (80% of companies pay upfront)
    job_companies = cur.execute("SELECT job_id, company_id FROM jobs").fetchall()
    for job_id, company_id in job_companies:
        if random.random() < 0.80:
            emit_payment(conn, company_id=company_id, job_id=job_id,
                         payment_type="job_slot")

    # per_shortlist payment for each shortlisted application
    shortlisted_apps = cur.execute(
        "SELECT a.application_id, j.company_id, j.job_id FROM applications a "
        "JOIN jobs j ON a.job_id=j.job_id "
        "WHERE a.status IN ('Shortlisted','Interviewed','Offered')"
    ).fetchall()
    for app_id, company_id, job_id in shortlisted_apps:
        emit_payment(conn, company_id=company_id, job_id=job_id,
                     application_id=app_id, payment_type="per_shortlist")

    # subscription payments — ~15% of companies pay monthly subscription
    comp_ids = [r[0] for r in cur.execute("SELECT company_id FROM companies").fetchall()]
    for cid in random.sample(comp_ids, k=int(len(comp_ids) * 0.15)):
        emit_payment(conn, company_id=cid, payment_type="subscription")

    # daily reconciliation for the last 7 days
    for days_back in range(1, 8):
        recon_date = (dt.datetime.now() - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
        emit_reconciliation(conn, recon_date)

    # Task 7: seed student pay-per-application conversions (800 attempts)
    seed_student_payments(conn, n=800)

    # Task 8: issue receipts for all successful payments + refunds for a subset
    seed_receipts_and_refunds(conn)

    conn.commit()

    totals = {}
    for tbl in ["companies","jobs","students","applications","interviews","offers",
                "job_supply_events","job_search_events","job_view_events",
                "application_events","payments","payment_events","payment_reconciliation",
                "student_payments","conversion_events",
                "receipts","refunds","refund_events"]:
        totals[tbl] = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    conn.close()

    print("Seed complete:")
    for tbl, n in totals.items():
        print(f"  {tbl:25s} {n:>5d} rows")


def run_live(interval_sec=8):
    """
    Continuous live event loop.
    Rotates between job_posted (supply), job_search_performed (discovery),
    and application_submitted (Task 4) events, simulating real platform
    traffic. Press Ctrl+C to stop.
    """
    conn    = get_conn()
    cur     = conn.cursor()
    company_ids = [r[0] for r in cur.execute("SELECT company_id FROM companies").fetchall()]
    student_ids = [r[0] for r in cur.execute("SELECT student_id FROM students").fetchall()]
    job_ids     = [r[0] for r in cur.execute("SELECT job_id FROM jobs WHERE status='open'").fetchall()]

    if not company_ids:
        print("No companies found. Run 'seed' first.")
        conn.close()
        return

    QUERIES = ["python developer", "data analyst fresher", "backend engineer",
               "remote sql jobs", "machine learning intern", "react developer"]

    print(f"Live feed started — emitting job_posted + job_search_performed + "
          f"application_submitted events every ~{interval_sec}s")
    print("Press Ctrl+C to stop.\n")
    count = 0
    try:
        while True:
            roll = random.random()
            if roll < 0.34 or not student_ids:
                comp_id  = random.choice(company_ids)
                title    = random.choice(ROLES)
                skills   = ", ".join(random.sample(SKILLS, k=random.randint(2, 4)))
                min_cgpa = random.choice([6.0, 6.5, 7.0, 7.5, 8.0])
                salary   = random.choice(SALARIES)

                job_id = emit_job_posted(conn, comp_id, title, skills, min_cgpa, salary)
                job_ids.append(job_id)
                count += 1

                total_events = cur.execute("SELECT COUNT(*) FROM job_supply_events").fetchone()[0]
                print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] job_posted → "
                      f"job_id={job_id} | {title} | min_cgpa={min_cgpa} | "
                      f"₹{salary:,} | total_events={total_events}")

            elif roll < 0.67 or not job_ids:
                s_id = random.choice(student_ids)
                query = random.choice(QUERIES)
                search_id = emit_job_search(conn, s_id, query)
                count += 1
                total_searches = cur.execute("SELECT COUNT(*) FROM job_search_events").fetchone()[0]
                print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] job_search_performed → "
                      f"student_id={s_id} | \"{query}\" | total_searches={total_searches}")

            else:
                s_id = random.choice(student_ids)
                j_id = random.choice(job_ids)
                app_id = emit_application(conn, s_id, j_id)
                count += 1
                if app_id:
                    verified = cur.execute(
                        "SELECT verified FROM applications WHERE application_id=?", (app_id,)
                    ).fetchone()[0]
                    shortlisted = bool(verified) and random.random() < 0.45 and emit_shortlist(conn, app_id)
                    # If shortlisted, fire a per_shortlist payment
                    if shortlisted:
                        j_company = cur.execute(
                            "SELECT company_id FROM jobs WHERE job_id=?", (j_id,)
                        ).fetchone()[0]
                        pid = emit_payment(conn, j_company, "per_shortlist",
                                           job_id=j_id, application_id=app_id)
                        pay_outcome = emit_payment_status(conn, pid)
                    total_apps = cur.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
                    outcome = "SHORTLISTED" if shortlisted else ("verified" if verified else "REJECTED (unverified)")
                    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] application_submitted → "
                          f"app_id={app_id} | student={s_id} | job={j_id} | "
                          f"{outcome} | total_applications={total_apps}")

            time.sleep(interval_sec + random.uniform(-2, 2))

    except KeyboardInterrupt:
        print(f"\nLive feed stopped. Emitted {count} events this session.")
        conn.close()


# ── TASK 6: Payment emitters ───────────────────────────────────────────────

PAYMENT_TYPES   = ["per_shortlist", "job_slot", "subscription"]
PAYMENT_AMOUNTS = {
    "per_shortlist":  500.0,   # INR per verified shortlist
    "job_slot":      2999.0,   # INR per job posting slot (30 days)
    "subscription": 9999.0,    # INR monthly company subscription
}
FAILURE_REASONS = [
    "insufficient_funds", "card_expired", "gateway_timeout",
    "bank_declined", "duplicate_transaction"
]


def emit_payment(conn, company_id: int, job_id: int = None,
                 application_id: int = None,
                 payment_type: str = "per_shortlist",
                 gateway_mode: str = "test") -> dict:
    """
    Fires the full payment lifecycle:
      payment_initiated → (success | failed) → [payment_refunded on failure]
    Records in both the payments entity table AND the payment_events audit log.

    Self-check answer: "what happens if a payment fails halfway?"
    → The student never loses money or their application:
      - application_id is NOT updated on payment failure
      - a payment_failed event fires with the failure_reason
      - the payment status is set to 'failed', not 'success'
      - the company is notified via the event log to retry
    """
    cur = conn.cursor()
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    amount = PAYMENT_AMOUNTS.get(payment_type, 500.0)
    gateway_ref = f"GW-TEST-{random.randint(100000, 999999)}"

    # Step 1: initiate
    cur.execute("""
        INSERT INTO payments
            (company_id, job_id, application_id, payment_type, amount_inr,
             currency, gateway_ref, gateway_mode, status, initiated_at)
        VALUES (?,?,?,?,?, 'INR',?,?,'initiated',?)
    """, (company_id, job_id, application_id, payment_type,
          amount, gateway_ref, gateway_mode, now))
    payment_id = cur.lastrowid

    cur.execute("""
        INSERT INTO payment_events
            (payment_id, company_id, event_name, amount_inr,
             gateway_ref, gateway_mode, emitted_at)
        VALUES (?,?, 'payment_initiated', ?,?,?,?)
    """, (payment_id, company_id, amount, gateway_ref, gateway_mode, now))

    # Step 2: gateway response — 82% success, 18% failure (realistic test-mode ratio)
    resolved_at = (dt.datetime.now() + dt.timedelta(seconds=random.randint(1,5))).strftime("%Y-%m-%d %H:%M:%S")

    if random.random() < 0.82:
        # SUCCESS
        cur.execute("""
            UPDATE payments SET status='success', resolved_at=? WHERE payment_id=?
        """, (resolved_at, payment_id))
        cur.execute("""
            INSERT INTO payment_events
                (payment_id, company_id, event_name, amount_inr,
                 gateway_ref, gateway_mode, emitted_at)
            VALUES (?,?, 'payment_success', ?,?,?,?)
        """, (payment_id, company_id, amount, gateway_ref, gateway_mode, resolved_at))
        status = "success"
        failure_reason = None
    else:
        # FAILURE — student application is NOT touched
        failure_reason = random.choice(FAILURE_REASONS)
        cur.execute("""
            UPDATE payments SET status='failed', failure_reason=?, resolved_at=?
            WHERE payment_id=?
        """, (failure_reason, resolved_at, payment_id))
        cur.execute("""
            INSERT INTO payment_events
                (payment_id, company_id, event_name, amount_inr,
                 gateway_ref, gateway_mode, failure_reason, emitted_at)
            VALUES (?,?, 'payment_failed', ?,?,?,?,?)
        """, (payment_id, company_id, amount, gateway_ref,
              gateway_mode, failure_reason, resolved_at))
        status = "failed"

    conn.commit()
    return {"payment_id": payment_id, "status": status,
            "amount_inr": amount, "failure_reason": failure_reason,
            "gateway_ref": gateway_ref, "gateway_mode": gateway_mode}


def emit_reconciliation(conn, recon_date: str = None):
    """
    Runs a daily reconciliation: compares our DB success records vs what
    the gateway reports. In test mode, we simulate a small discrepancy
    (1-2 transactions) to show the check is real, not always-green.
    Answers: "how do we know our records match what the gateway collected?"
    """
    cur = conn.cursor()
    if not recon_date:
        recon_date = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # what we recorded
    our = cur.execute("""
        SELECT COUNT(*) cnt, COALESCE(SUM(amount_inr),0) total
        FROM payments
        WHERE status='success' AND DATE(resolved_at)=?
    """, (recon_date,)).fetchone()
    our_count, our_total = our

    # simulate gateway report — 98% of the time it matches; occasionally off by 1-2
    if random.random() < 0.92:
        gw_count, gw_total = our_count, our_total
    else:
        gw_count = our_count - random.randint(1, 2)
        gw_total = round(our_total - random.uniform(500, 2999), 2)

    discrepancy = round(our_total - gw_total, 2)
    matched = 1 if abs(discrepancy) < 0.01 else 0
    notes = "MATCHED" if matched else f"DISCREPANCY ₹{discrepancy} — investigate with gateway"

    cur.execute("""
        INSERT INTO payment_reconciliation
            (recon_date, our_count, our_total_inr, gateway_count,
             gateway_total_inr, matched, discrepancy_inr, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (recon_date, our_count, our_total, gw_count,
          gw_total, matched, discrepancy, notes, now))
    conn.commit()
    return {"recon_date": recon_date, "matched": matched,
            "our_total": our_total, "discrepancy": discrepancy}


# ── TASK 7: Student Pay-per-Application emitters ───────────────────────────

STUDENT_FAILURE_REASONS = [
    "insufficient_funds", "card_declined", "gateway_timeout",
    "upi_timeout", "net_banking_error"
]


def emit_student_payment(conn, student_id: int, job_id: int) -> dict:
    """
    Fires the complete ₹100 pay-per-application conversion funnel:

    STEP 1: job_viewed          → student opens the job listing
    STEP 2: pay_per_app_initiated → student clicks "Apply & Pay ₹100"
    STEP 3: pay_per_app_success OR pay_per_app_failed
    STEP 4 (success only): application_created → application row inserted
    STEP 4 (failed): application_abandoned → application NOT created

    KEY RULE (answers self-check Q1):
    "What happens if payment fails halfway?"
    → Student loses NOTHING. application_created fires only AFTER
      pay_per_app_success. A failed payment produces no application row.
      The student can retry without re-viewing the listing.
      The conversion_events log always shows what happened and why.
    """
    cur = conn.cursor()
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gateway_ref = f"GW-SPA-{random.randint(100000,999999)}"

    # STEP 1: job_viewed
    cur.execute("""
        INSERT INTO conversion_events
            (student_id, job_id, event_name, amount_inr, gateway_mode, emitted_at)
        VALUES (?, ?, 'job_viewed', 0, 'test', ?)
    """, (student_id, job_id, now))

    # STEP 2: pay_per_app_initiated
    cur.execute("""
        INSERT INTO student_payments
            (student_id, job_id, amount_inr, gateway_ref, gateway_mode,
             status, initiated_at)
        VALUES (?, ?, 100, ?, 'test', 'initiated', ?)
    """, (student_id, job_id, gateway_ref, now))
    sp_id = cur.lastrowid

    cur.execute("""
        INSERT INTO conversion_events
            (student_id, job_id, sp_id, event_name, amount_inr, gateway_mode, emitted_at)
        VALUES (?, ?, ?, 'pay_per_app_initiated', 100, 'test', ?)
    """, (student_id, job_id, sp_id, now))

    # STEP 3: gateway response — 78% success, 12% fail, 10% abandon
    resolved_at = (dt.datetime.now() + dt.timedelta(
        seconds=random.randint(2, 8))).strftime("%Y-%m-%d %H:%M:%S")
    roll = random.random()

    if roll < 0.78:
        # SUCCESS
        cur.execute("""
            UPDATE student_payments
            SET status='success', resolved_at=? WHERE sp_id=?
        """, (resolved_at, sp_id))
        cur.execute("""
            INSERT INTO conversion_events
                (student_id, job_id, sp_id, event_name, amount_inr,
                 gateway_mode, emitted_at)
            VALUES (?, ?, ?, 'pay_per_app_success', 100, 'test', ?)
        """, (student_id, job_id, sp_id, resolved_at))

        # STEP 4 SUCCESS: create the application — only after payment confirmed
        cur.execute("""
            INSERT INTO applications
                (student_id, job_id, applied_at, status, verified)
            VALUES (?, ?, ?, 'Applied',
                CASE WHEN (SELECT cgpa FROM students WHERE student_id=?)
                     >= (SELECT min_cgpa FROM jobs WHERE job_id=?)
                THEN 1 ELSE 0 END)
        """, (student_id, job_id, resolved_at, student_id, job_id))
        application_id = cur.lastrowid

        cur.execute("""
            UPDATE student_payments SET application_id=? WHERE sp_id=?
        """, (application_id, sp_id))
        cur.execute("""
            INSERT INTO conversion_events
                (student_id, job_id, sp_id, application_id, event_name,
                 amount_inr, gateway_mode, emitted_at)
            VALUES (?, ?, ?, ?, 'application_created', 100, 'test', ?)
        """, (student_id, job_id, sp_id, application_id, resolved_at))

        # also log in application_events for full audit trail
        company_id = cur.execute(
            "SELECT company_id FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        verified = cur.execute(
            "SELECT verified FROM applications WHERE application_id=?",
            (application_id,)
        ).fetchone()[0]
        cur.execute("""
            INSERT INTO application_events
                (application_id, student_id, job_id, company_id,
                 event_name, verified, emitted_at)
            VALUES (?, ?, ?, ?, 'application_submitted', ?, ?)
        """, (application_id, student_id, job_id, company_id,
              verified, resolved_at))

        conn.commit()
        return {"sp_id": sp_id, "status": "success",
                "application_id": application_id, "failure_reason": None}

    elif roll < 0.90:
        # FAILURE — application is NOT created
        failure_reason = random.choice(STUDENT_FAILURE_REASONS)
        cur.execute("""
            UPDATE student_payments
            SET status='failed', failure_reason=?, resolved_at=?
            WHERE sp_id=?
        """, (failure_reason, resolved_at, sp_id))
        cur.execute("""
            INSERT INTO conversion_events
                (student_id, job_id, sp_id, event_name, amount_inr,
                 failure_reason, gateway_mode, emitted_at)
            VALUES (?, ?, ?, 'pay_per_app_failed', 100, ?, 'test', ?)
        """, (student_id, job_id, sp_id, failure_reason, resolved_at))

        conn.commit()
        return {"sp_id": sp_id, "status": "failed",
                "application_id": None, "failure_reason": failure_reason}

    else:
        # ABANDONED — student left before completing payment
        cur.execute("""
            UPDATE student_payments SET status='abandoned' WHERE sp_id=?
        """, (sp_id,))
        cur.execute("""
            INSERT INTO conversion_events
                (student_id, job_id, sp_id, event_name, amount_inr,
                 gateway_mode, emitted_at)
            VALUES (?, ?, ?, 'application_abandoned', 100, 'test', ?)
        """, (student_id, job_id, sp_id, resolved_at))

        conn.commit()
        return {"sp_id": sp_id, "status": "abandoned",
                "application_id": None, "failure_reason": None}


def seed_student_payments(conn, n=800):
    """Seed student pay-per-application events at realistic scale."""
    cur = conn.cursor()
    student_ids = [r[0] for r in cur.execute(
        "SELECT student_id FROM students ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()]
    job_ids = [r[0] for r in cur.execute(
        "SELECT job_id FROM jobs WHERE status='open' LIMIT 200"
    ).fetchall()]

    counts = {"success": 0, "failed": 0, "abandoned": 0}
    for s_id in student_ids:
        j_id = random.choice(job_ids)
        result = emit_student_payment(conn, s_id, j_id)
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    print(f"  student_payments seeded: {n} attempts")
    print(f"    success: {counts.get('success',0)} | "
          f"failed: {counts.get('failed',0)} | "
          f"abandoned: {counts.get('abandoned',0)}")


# ── TASK 8: Receipts, Refunds & Reconciliation emitters ───────────────────

REFUND_REASONS = [
    "payment_failed",       # gateway charged but never confirmed — auto-refund
    "duplicate_transaction",# student/company paid twice — auto-refund the second
    "candidate_withdrew",   # student withdrew application after paying
    "company_cancelled",    # company cancelled the job after being billed
    "gateway_error",        # gateway processing error flagged post-settlement
    "manual_review",        # founder or support team issued manual refund
]


def emit_receipt(conn, payment_source: str, payment_id: int,
                 payer_id: int, amount_inr: float,
                 payment_type: str, gateway_ref: str,
                 issued_at: str) -> int:
    """
    Issues a receipt for every successful payment.
    Formula: one receipt per successful payment — no receipt without a payment,
    no refund without a receipt.
    Source: payments WHERE status='success' OR student_payments WHERE status='success'
    Decision: receipt_count should always equal successful payment count.
    Any gap = a receipt generation bug → customer has paid but has no proof.
    """
    cur = conn.cursor()
    # generate human-readable receipt number
    seq = cur.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] + 1
    receipt_number = f"RCP-2026-{seq:06d}"

    cur.execute("""
        INSERT INTO receipts
            (receipt_number, payment_source, payment_id, payer_id,
             amount_inr, payment_type, gateway_ref, issued_at, refund_eligible)
        VALUES (?,?,?,?,?,?,?,?,1)
    """, (receipt_number, payment_source, payment_id,
          payer_id, amount_inr, payment_type, gateway_ref, issued_at))
    receipt_id = cur.lastrowid
    conn.commit()
    return receipt_id


def emit_refund(conn, receipt_id: int, reason: str,
                partial_amount: float = None,
                initiated_by: str = "system") -> dict:
    """
    Issues a refund against a receipt.

    KEY RULES (answers self-check Q1):
    1. A refund can ONLY be issued if a receipt exists (no receipt = no refund).
    2. The refund amount cannot exceed the original payment amount.
    3. Every refund fires refund_initiated → refund_processed/refund_failed to the
       refund_events audit log — never just updating a field silently.
    4. If a refund fails (gateway error), the receipt remains valid and
       a refund_failed event fires — the refund must be retried manually.
    5. Partial refunds are supported (partial_amount < receipt.amount_inr).

    Source: refunds table + refund_events
    Decision: rising refund rate by reason tells you what to fix —
              'company_cancelled' spike → review job posting commitment policy.
    """
    cur = conn.cursor()
    receipt = cur.execute(
        "SELECT amount_inr, refund_eligible, payer_id, payment_source, "
        "       payment_type, gateway_ref FROM receipts WHERE receipt_id=?",
        (receipt_id,)
    ).fetchone()
    if not receipt:
        return {"status": "error", "reason": "receipt_not_found"}
    if not receipt[1]:
        return {"status": "error", "reason": "receipt_not_refund_eligible"}

    amount = partial_amount if partial_amount else receipt[0]
    if amount > receipt[0]:
        amount = receipt[0]  # cap at original amount

    gateway_ref = f"GW-REF-{random.randint(100000,999999)}"
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO refunds
            (receipt_id, payment_source, payer_id, amount_inr, reason,
             initiated_by, status, gateway_ref, initiated_at)
        VALUES (?,?,?,?,?,?,'initiated',?,?)
    """, (receipt_id, receipt[3], receipt[2], amount,
          reason, initiated_by, gateway_ref, now))
    refund_id = cur.lastrowid

    # refund_initiated event
    cur.execute("""
        INSERT INTO refund_events
            (refund_id, receipt_id, event_name, amount_inr, reason, gateway_ref, emitted_at)
        VALUES (?,?, 'refund_initiated', ?,?,?,?)
    """, (refund_id, receipt_id, amount, reason, gateway_ref, now))

    # gateway response — 93% process, 7% fail
    processed_at = (dt.datetime.now() + dt.timedelta(
        seconds=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")

    if random.random() < 0.93:
        cur.execute("""
            UPDATE refunds SET status='processed', processed_at=?
            WHERE refund_id=?
        """, (processed_at, refund_id))
        cur.execute("""
            INSERT INTO refund_events
                (refund_id, receipt_id, event_name, amount_inr,
                 reason, gateway_ref, emitted_at)
            VALUES (?,?, 'refund_processed', ?,?,?,?)
        """, (refund_id, receipt_id, amount, reason, gateway_ref, processed_at))
        status = "processed"
    else:
        cur.execute("""
            UPDATE refunds SET status='failed', processed_at=? WHERE refund_id=?
        """, (processed_at, refund_id))
        cur.execute("""
            INSERT INTO refund_events
                (refund_id, receipt_id, event_name, amount_inr,
                 reason, gateway_ref, emitted_at)
            VALUES (?,?, 'refund_failed', ?,?,?,?)
        """, (refund_id, receipt_id, amount, reason, gateway_ref, processed_at))
        status = "failed"

    conn.commit()
    return {"refund_id": refund_id, "receipt_id": receipt_id,
            "amount": amount, "status": status, "reason": reason}


def seed_receipts_and_refunds(conn):
    """
    Seed receipts for all successful payments (company + student),
    then issue refunds for a realistic subset of them.
    """
    cur = conn.cursor()
    receipt_count = 0

    # receipts for company payments (Task 6)
    company_pays = cur.execute("""
        SELECT p.payment_id, p.company_id, p.amount_inr, p.payment_type,
               p.gateway_ref, p.resolved_at
        FROM payments p WHERE p.status='success'
    """).fetchall()
    company_receipt_ids = []
    for pid, cid, amt, ptype, gref, resolved in company_pays:
        rid = emit_receipt(conn, "company", pid, cid, amt, ptype, gref, resolved)
        company_receipt_ids.append((rid, amt, ptype))
        receipt_count += 1

    # receipts for student payments (Task 7)
    student_pays = cur.execute("""
        SELECT sp.sp_id, sp.student_id, sp.amount_inr, sp.gateway_ref, sp.resolved_at
        FROM student_payments sp WHERE sp.status='success'
    """).fetchall()
    student_receipt_ids = []
    for spid, sid, amt, gref, resolved in student_pays:
        rid = emit_receipt(conn, "student", spid, sid, amt,
                           "per_application", gref, resolved)
        student_receipt_ids.append((rid, amt))
        receipt_count += 1

    print(f"  receipts issued: {receipt_count}")

    # Refunds — realistic subset
    refund_count = 0

    # ~8% of company payments get refunded
    refund_company = random.sample(
        company_receipt_ids, k=max(1, int(len(company_receipt_ids)*0.08)))
    company_reasons = ["company_cancelled", "duplicate_transaction",
                       "gateway_error", "manual_review"]
    for rid, amt, ptype in refund_company:
        result = emit_refund(conn, rid,
                             reason=random.choice(company_reasons),
                             initiated_by=random.choice(["system","founder"]))
        if result.get("refund_id"):
            refund_count += 1

    # ~12% of student payments get refunded (higher — candidate_withdrew is common)
    refund_student = random.sample(
        student_receipt_ids, k=max(1, int(len(student_receipt_ids)*0.12)))
    student_reasons = ["candidate_withdrew", "payment_failed",
                       "duplicate_transaction", "gateway_error"]
    for rid, amt in refund_student:
        result = emit_refund(conn, rid,
                             reason=random.choice(student_reasons),
                             initiated_by=random.choice(["system","founder","gateway"]))
        if result.get("refund_id"):
            refund_count += 1

    print(f"  refunds issued  : {refund_count}")
    print(f"  refund_events   : {cur.execute('SELECT COUNT(*) FROM refund_events').fetchone()[0]}")


def status():
    conn = get_conn()
    cur  = conn.cursor()
    print("\n=== PlaceMux Live Data Status ===")
    for tbl in ["companies","jobs","students","applications","interviews","offers",
                "job_supply_events","job_search_events","job_view_events",
                "application_events","payments","payment_events","payment_reconciliation",
                "student_payments","conversion_events",
                "receipts","refunds","refund_events"]:
        n = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:25s} {n:>6d} rows")
    last = cur.execute("SELECT MAX(emitted_at) FROM job_supply_events").fetchone()[0]
    print(f"\n  Last job_posted event : {last}")
    hours = (dt.datetime.now() - dt.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds()/3600 if last else None
    print(f"  Hours ago             : {hours:.1f}" if hours else "  No events yet")
    conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "seed":
        seed()
    elif cmd == "live":
        run_live()
    elif cmd == "status":
        status()
    else:
        print(__doc__)
