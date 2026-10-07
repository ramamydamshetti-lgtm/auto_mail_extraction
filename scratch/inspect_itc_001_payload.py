import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()

c.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE job_id LIKE '%ITC%' OR payload_json LIKE '%ITC%'")
rows = c.fetchall()

print(f"Found {len(rows)} ITC rows in metaforge_requirements.db:\n")

for jid, pjson in rows:
    p = json.loads(pjson)
    cjd = p.get('client_jd_id') or jid
    print(f"=== JOB ID: {jid} | CLIENT JD ID: {cjd} ===")
    print(f"  requirement_from : {p.get('requirement_from')}")
    print(f"  client_poc       : {p.get('client_poc')}")
    print(f"  client_lead_poc  : {p.get('client_lead_poc')}")
    print(f"  job_title        : {p.get('job_title')}")
    print()

conn.close()
