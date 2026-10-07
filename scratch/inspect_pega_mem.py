import sqlite3
import json

conn = sqlite3.connect('data/processed_messages.db')
rows = conn.execute("SELECT id, requirement_from, job_title_norm, created_at, payload_json FROM requirement_memory WHERE job_title_norm LIKE '%pega%'").fetchall()
print(f"Pega rows in requirement_memory: {len(rows)}")
for r in rows:
    p = json.loads(r[4])
    print(f"id={r[0]} from={r[1]} title={r[2]} created_at={r[3]}")
    print(f"  cjd={p.get('client_jd_id')}")
    print(f"  mandatory_skills={p.get('mandatory_skills')}")
    print(f"  skills={p.get('skills')}")
    print(f"  prov={p.get('_provenance')}")
