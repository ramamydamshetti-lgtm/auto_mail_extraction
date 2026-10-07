import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()

for r in rows:
    p = json.loads(r['payload_json'])
    st = str(p.get('job_status') or '')
    if st.lower() not in ('open', 'hold', 'closed', 'reopen', 'active', 'cancelled', 'on hold', 'on-hold', 'not specified'):
        print(f"Job: {r['job_id']} | ClientID: {r['client_jd_id']} | Weird status: {st[:80]}")

conn.close()
