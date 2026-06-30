"""
Streamlit Cloud entry point.
Auto-creates and seeds the database on first run, then launches the dashboard.
This file exists so Streamlit Cloud can run the app without any manual setup.
"""
import os, subprocess, sys

DB_PATH = os.path.join(os.path.dirname(__file__), "placemux.db")

# On Streamlit Cloud the DB doesn't exist — create and seed it automatically
if not os.path.exists(DB_PATH):
    subprocess.run([sys.executable, "create_database.py"], check=True)
    subprocess.run([sys.executable, "live_data.py", "seed"], check=True)

# Now run the real dashboard
exec(open("dashboard.py").read())
