import sqlite3, json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT job_id, client_jd_id, payload_json, created_at, updated_at FROM metaforge_requirements').fetchall()

for r in rows:
    p = json.loads(r['payload_json'])
    title = str(p.get('job_title') or '')
    loc = str(p.get('location') or '')
    c = str(p.get('requirement_from') or '')
    cjd = str(p.get('client_jd_id') or r['client_jd_id'] or '')
    if 'co' in title.lower() or 'management accounting' in title.lower():
        print(f"ID={r['job_id']:16s} | CJD={cjd:12s} | Client={c:12s} | Loc={loc:25s} | Title={title}")

print("\n--- Checking pending_reviews ---")
conn2 = sqlite3.connect('data/processed_messages.db')
conn2.row_factory = sqlite3.Row
p_rows = conn2.execute('SELECT id, graph_id, job_id, client_jd_id, payload_json, review_fields, created_at FROM pending_reviews').fetchall()
print(f"Total pending_reviews: {len(p_rows)}")
for pr in p_rows:
    p = json.loads(pr['payload_json'])
    title = str(p.get('job_title') or '')
    loc = str(p.get('location') or '')
    c = str(p.get('requirement_from') or '')
    cjd = str(p.get('client_jd_id') or pr['client_jd_id'] or '')
    if 'accounting' in title.lower() or 'plm' in title.lower() or 'mysore' in loc.lower() or 'mumbai' in loc.lower():
        print(f"PENDING id={pr['id']} | CJD={cjd:12s} | Client={c:12s} | Loc={loc:25s} | Title={title}")
