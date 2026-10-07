import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row

for jid in ['2026/09/30-001', '2026/09/30-045', '2026/09/30-046']:
    r = conn.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (jid,)).fetchone()
    if r:
        p = json.loads(r['payload_json'])
        print(f"=== {jid} ===")
        print(f"  created_at: {r['created_at']}")
        print(f"  client_jd_id: {r['client_jd_id']}")
        print(f"  graphMessageId: {p.get('graphMessageId')}")
        print(f"  internetMessageId: {p.get('internetMessageId')}")
        print(f"  subject: {p.get('subject')}")
        print(f"  job_title: {p.get('job_title')}")
        print(f"  body snippet: {str(p.get('bodyText') or p.get('body'))[:200]}")

conn.close()
