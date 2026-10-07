import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM metaforge_requirements WHERE job_id = '2026-09-30-044' OR client_jd_id = 'RQ056293'").fetchall()

for r in rows:
    print("JOB_ID:", r['job_id'])
    print("CREATED_AT:", r['created_at'])
    print("CLIENT_JD_ID:", r['client_jd_id'])
    p = json.loads(r['payload_json'])
    print("demand_received_date:", p.get('demand_received_date'))
    print("receivedDateTime:", p.get('receivedDateTime'))
    print("email_received_iso:", p.get('email_received_iso'))
    prov = p.get('_provenance') or {}
    print("_provenance:", prov)

conn.close()
