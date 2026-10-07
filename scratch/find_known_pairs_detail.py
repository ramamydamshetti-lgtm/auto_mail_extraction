import sqlite3, json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT job_id, client_jd_id, payload_json, created_at, updated_at FROM metaforge_requirements").fetchall()

print("=== CHECKING DUPLICATES IN METAFORGE_REQUIREMENTS ===")
for r in rows:
    p = json.loads(r['payload_json'])
    client = p.get('requirement_from') or ''
    title = p.get('job_title') or ''
    loc = str(p.get('location') or '')
    cjd = p.get('client_jd_id') or r['client_jd_id'] or ''
    
    if ('plm' in title.lower() and 'mysore' in loc.lower()) or \
       ('management accounting' in title.lower() and ('mumbai' in loc.lower() or 'pan india' in loc.lower())):
        print(f"Job_id={r['job_id']:16s} | CJD={cjd:16s} | Client={client:12s} | Loc={loc:20s} | Title={title:35s} | Created={r['created_at']}")

conn.close()
