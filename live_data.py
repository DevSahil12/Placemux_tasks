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

    totals = {}
    for tbl in ["companies","jobs","students","applications","interviews","offers",
                "job_supply_events","job_search_events","job_view_events","application_events"]:
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
                    # 45% of verified applications get shortlisted immediately, live
                    shortlisted = bool(verified) and random.random() < 0.45 and emit_shortlist(conn, app_id)
                    total_apps = cur.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
                    outcome = "SHORTLISTED" if shortlisted else ("verified" if verified else "REJECTED (unverified)")
                    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] application_submitted → "
                          f"app_id={app_id} | student={s_id} | job={j_id} | "
                          f"{outcome} | total_applications={total_apps}")

            time.sleep(interval_sec + random.uniform(-2, 2))

    except KeyboardInterrupt:
        print(f"\nLive feed stopped. Emitted {count} events this session.")
        conn.close()


def status():
    conn = get_conn()
    cur  = conn.cursor()
    print("\n=== PlaceMux Live Data Status ===")
    for tbl in ["companies","jobs","students","applications","interviews","offers",
                "job_supply_events","job_search_events","job_view_events","application_events"]:
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
