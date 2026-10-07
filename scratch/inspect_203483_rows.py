import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
cur = conn.cursor()
rows = cur.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE payload_json LIKE '%203483-1%'").fetchall()
print(f"Total rows matching 203483-1: {len(rows)}")
for r in rows:
    p = json.loads(r[1])
    print(f"job_id: {r[0]} | client_jd_id: {p.get('client_jd_id')} | title: {p.get('job_title')} | status: {p.get('job_status')} | subj: {p.get('subject')}")
conn.close()
