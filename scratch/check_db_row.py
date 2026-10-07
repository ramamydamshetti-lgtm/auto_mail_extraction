import sqlite3
import json

conn = sqlite3.connect("data/metaforge_requirements.db")
c = conn.cursor()
c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = '2026/10/05-011' OR client_jd_id = '2026/10/05-011'")
row = c.fetchone()
if not row:
    print("Row not found!")
else:
    print("Job ID:", row[0])
    p = json.loads(row[2])
    fields = [
        "job_title",
        "number_of_positions",
        "overall_experience",
        "experience",
        "mandatory_skills",
        "skills",
        "monthly_budget",
        "yearly_budget",
        "work_mode",
        "notice_period",
        "location",
    ]
    for f in fields:
        print(f"{f}: {repr(p.get(f))}")
conn.close()
