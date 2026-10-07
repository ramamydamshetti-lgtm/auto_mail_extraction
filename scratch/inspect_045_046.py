import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row

for req_id in ['2026-09-30-045', '2026-09-30-046', '2026/09/30-045', '2026/09/30-046']:
    rows = conn.execute("SELECT * FROM metaforge_requirements WHERE job_id = ? OR job_id = ?", (req_id, req_id.replace('/', '-'))).fetchall()
    for r in rows:
        print(f"==================== {r['job_id']} ====================")
        p = json.loads(r['payload_json'])
        for k in ['job_title', 'subject', 'role', 'client_jd_id', 'job_status', 'requirement_from', 'from', 'mandatory_skills', 'skills']:
            print(f"  {k}: {p.get(k)}")
        print("\n  FULL EMAIL BODY:")
        body = p.get('bodyText') or p.get('body') or ""
        print(body[:2000])
        print("\n" + "="*50)

conn.close()
