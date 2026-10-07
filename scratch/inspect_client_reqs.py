import sqlite3, json

conn = sqlite3.connect('data/processed_messages.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM client_requirements").fetchall()
print(f"Total client_requirements: {len(rows)}")
for r in rows:
    p = json.loads(r['payload_json'])
    client = r['requirement_from']
    title = p.get('job_title') or ''
    loc = p.get('location') or ''
    cjd = r['client_jd_id']
    if 'accounting' in title.lower() or 'mumbai' in str(loc).lower():
        print(f"CJD: {cjd} | Client: {client} | Title: {title} | Loc: {loc}")

conn.close()
