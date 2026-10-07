import sqlite3
import json

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT id, job_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%' AND (lower(payload_json) LIKE '%ltts%' OR lower(payload_json) LIKE '%l&t%')")
pr_rows = c_pm.fetchall()

print(f"======================================================================")
print(f"TOTAL LTTS REQUIREMENTS EXTRACTED TODAY (2026-09-29): {len(pr_rows)}")
print(f"======================================================================")

for idx, (pid, jid, pjson, ca) in enumerate(pr_rows, 1):
    p = json.loads(pjson)
    title = p.get('job_title') or 'N/A'
    loc = p.get('location') or 'Not specified'
    exp = p.get('overall_experience') or 'N/A'
    skills = p.get('mandatory_skills') or 'N/A'
    print(f"{idx:2d}. [Job ID: {jid}]")
    print(f"    Title   : {title}")
    print(f"    Location: {loc}")
    print(f"    Exp     : {exp}")
    print(f"    Skills  : {skills}")
    print()

conn_pm.close()
