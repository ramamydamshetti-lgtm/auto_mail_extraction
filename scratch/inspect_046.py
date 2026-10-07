import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
cur = conn.cursor()
row = cur.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE job_id LIKE '%046%'").fetchone()
if row:
    print("JOB_ID:", row[0])
    p = json.loads(row[1])
    print(json.dumps(p, indent=2))
else:
    print("Row 046 not found")
conn.close()
