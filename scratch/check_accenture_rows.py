import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
rows = conn.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE payload_json LIKE '%209160-1%' OR payload_json LIKE '%Accenture open demands for 30th Sep%'").fetchall()
print(f"Total matching rows: {len(rows)}")
for r in rows:
    p = json.loads(r[2])
    print(f"DB job_id: {r[0]} | DB client_jd_id: {r[1]} | payload client_jd_id: {p.get('client_jd_id')} | Title: {p.get('job_title')}")
conn.close()
