"""
PlaceMux — Realistic Data Generator
Generates scale data (not toy/happy-path) for all tables.
Also emits job_posted events into job_supply_events (Task 2 instrumentation).
"""
import random, sqlite3, datetime as dt
import pandas as pd
from faker import Faker

fake = Faker("en_IN")
random.seed(42)

TODAY    = dt.datetime(2026, 6, 18)
START    = TODAY - dt.timedelta(days=90)

INDUSTRIES   = ["SaaS", "Fintech", "EdTech", "E-commerce", "Healthtech", "Logistics", "Gaming"]
STATUSES_CO  = ["active", "active", "active", "inactive"]
ROLES        = ["Software Engineer", "Data Analyst", "Backend Developer", "Frontend Developer",
                "Data Scientist", "Product Manager", "DevOps Engineer", "QA Engineer",
                "ML Engineer", "Full Stack Developer", "Analyst Trainee", "Business Analyst"]
SKILLS_POOL  = ["Python", "SQL", "Java", "React", "AWS", "Docker", "Machine Learning",
                "Excel", "Power BI", "Node.js", "Kubernetes", "Go", "Tableau",
                "JavaScript", "C++", "MongoDB", "Spark", "Pandas", "TensorFlow"]
COLLEGES     = ["CGC Landran", "LPU", "Chandigarh University", "PEC Chandigarh",
                "UIET Panjab", "IIT Delhi", "NIT Kurukshetra", "Thapar University",
                "Amity University", "GGSIPU"]
APP_STATUSES = ["Applied", "Shortlisted", "Shortlisted", "Interviewed", "Offered", "Rejected"]
INT_STATUSES = ["Scheduled", "Completed", "Cancelled"]
OFF_STATUSES = ["Pending", "Accepted", "Declined"]

def rand_ts(start, end):
    delta = (end - start).total_seconds()
    return start + dt.timedelta(seconds=random.randint(0, max(int(delta), 1)))

def fmt(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S")

def generate(n_companies=80, n_jobs=300, n_students=600):
    conn = sqlite3.connect("placemux.db")
    cur  = conn.cursor()

    # ── companies ──────────────────────────────────────────────
    company_rows = []
    for i in range(1, n_companies + 1):
        company_rows.append((
            i,
            fake.company().replace(",", "").replace("'", "")[:40],
            random.choice(INDUSTRIES),
            fmt(rand_ts(START, TODAY)),
            random.choice(STATUSES_CO)
        ))
    cur.executemany(
        "INSERT INTO companies VALUES (?,?,?,?,?)", company_rows)

    # ── jobs ───────────────────────────────────────────────────
    job_rows = []
    for i in range(1, n_jobs + 1):
        comp_id   = random.randint(1, n_companies)
        skills    = ", ".join(random.sample(SKILLS_POOL, k=random.randint(2, 4)))
        min_cgpa  = round(random.choice([6.0, 6.5, 7.0, 7.5, 8.0]), 1)
        salary    = random.choice([300000, 400000, 500000, 600000, 800000, 1000000, 1200000])
        created   = fmt(rand_ts(START, TODAY))
        status    = random.choice(["open", "open", "open", "closed", "filled"])
        job_rows.append((i, comp_id, random.choice(ROLES), skills, min_cgpa, salary, created, status))
    cur.executemany(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)", job_rows)

    # ── job_supply_events (Task 2 instrumentation) ─────────────
    # One event per job posted — this is the event that fires when job_posted happens
    supply_events = []
    for j in job_rows:
        job_id, comp_id, title, skills, min_cgpa, salary, created, status = j
        supply_events.append((
            "job_posted", job_id, comp_id, title, skills, min_cgpa, salary, status, created
        ))
    cur.executemany(
        """INSERT INTO job_supply_events
           (event_name,job_id,company_id,job_title,skills,min_cgpa,salary,status,emitted_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        supply_events
    )

    # ── students ───────────────────────────────────────────────
    student_rows = []
    for i in range(1, n_students + 1):
        skills   = ", ".join(random.sample(SKILLS_POOL, k=random.randint(2, 5)))
        cgpa     = round(random.uniform(5.5, 10.0), 2)
        created  = fmt(rand_ts(START, TODAY))
        student_rows.append((i, fake.name(), random.choice(COLLEGES), cgpa, skills, created))
    cur.executemany(
        "INSERT INTO students VALUES (?,?,?,?,?,?)", student_rows)

    # ── applications ───────────────────────────────────────────
    app_rows  = []
    app_id    = 1
    seen_pairs = set()
    for s_id in range(1, n_students + 1):
        n_apps = random.randint(1, 5)
        job_sample = random.sample(range(1, n_jobs + 1), min(n_apps, n_jobs))
        for j_id in job_sample:
            if (s_id, j_id) in seen_pairs:
                continue
            seen_pairs.add((s_id, j_id))
            job_created = next(j[6] for j in job_rows if j[0] == j_id)
            applied_at  = fmt(rand_ts(
                max(dt.datetime.strptime(job_created, "%Y-%m-%d %H:%M:%S"), START), TODAY))
            status = random.choice(APP_STATUSES)
            app_rows.append((app_id, s_id, j_id, applied_at, status))
            app_id += 1
    cur.executemany(
        "INSERT INTO applications VALUES (?,?,?,?,?)", app_rows)

    # ── interviews (for Shortlisted/Interviewed/Offered apps) ──
    int_rows = []
    int_id   = 1
    for row in app_rows:
        a_id, s_id, j_id, applied_at, status = row
        if status in ("Interviewed", "Offered"):
            sched = fmt(rand_ts(
                dt.datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S") + dt.timedelta(days=2),
                TODAY))
            int_rows.append((int_id, a_id, sched, random.choice(INT_STATUSES)))
            int_id += 1
    cur.executemany(
        "INSERT INTO interviews VALUES (?,?,?,?)", int_rows)

    # ── offers ─────────────────────────────────────────────────
    off_rows = []
    off_id   = 1
    for row in app_rows:
        a_id, s_id, j_id, applied_at, status = row
        if status == "Offered":
            offered_at = fmt(rand_ts(
                dt.datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S") + dt.timedelta(days=7),
                TODAY))
            off_rows.append((off_id, a_id, offered_at, random.choice(OFF_STATUSES)))
            off_id += 1
    cur.executemany(
        "INSERT INTO offers VALUES (?,?,?,?)", off_rows)

    conn.commit()

    # Print summary
    for tbl in ["companies","jobs","students","applications","interviews","offers","job_supply_events"]:
        n = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:25s} {n:>5d} rows")

    conn.close()


if __name__ == "__main__":
    print("Generating data...")
    generate()
    print("Done.")
