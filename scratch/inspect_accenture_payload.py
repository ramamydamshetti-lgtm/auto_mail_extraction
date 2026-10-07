import sqlite3
import json

conn = sqlite3.connect(r'data\processed_messages.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM pending_reviews WHERE payload_json LIKE '%203501-1%'").fetchall()
print(f"Found {len(rows)} matching rows in pending_reviews:")
for r in rows:
    p = json.loads(r['payload_json'])
    print("--- RAW ITEM ---")
    print("job_id:", r['job_id'])
    print("job_title:", p.get("job_title"))
    print("client_jd_id:", p.get("client_jd_id"))
    print("requirement_from:", p.get("requirement_from"))
    print("email_subject:", p.get("email_subject") or p.get("subject"))
    print("bodyText snippet:\n", (p.get("bodyText") or p.get("body") or "")[:400])
