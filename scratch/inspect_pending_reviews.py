import sqlite3, json

conn = sqlite3.connect('data/processed_messages.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM pending_reviews").fetchall()
print(f"Total pending_reviews: {len(rows)}")
for r in rows:
    p = json.loads(r['payload_json'])
    print(r['id'], r['job_id'], r['client_jd_id'], p.get('requirement_from'), p.get('job_title'), p.get('location'))

conn.close()
