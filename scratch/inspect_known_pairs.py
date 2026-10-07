import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT job_id, client_jd_id, payload_json, created_at, updated_at FROM metaforge_requirements").fetchall()
print(f"Total rows in metaforge_requirements: {len(rows)}")

ltts_matches = []
accenture_matches = []

for r in rows:
    p = json.loads(r['payload_json'])
    client = p.get('requirement_from') or ''
    title = p.get('job_title') or ''
    loc = str(p.get('location') or '')
    cjd = p.get('client_jd_id') or r['client_jd_id'] or ''
    
    blob = f"{client} {title} {loc}".lower()
    if 'ltts' in blob and 'plm' in blob and 'mysore' in blob:
        ltts_matches.append((r['job_id'], cjd, title, loc, p.get('receivedDateTime') or r['created_at']))
    if 'accenture' in blob and 'management accounting' in blob and 'mumbai' in blob:
        accenture_matches.append((r['job_id'], cjd, title, loc, p.get('receivedDateTime') or r['created_at']))

print("\nLTTS PLM Mysore matches:")
for m in ltts_matches:
    print(" ", m)

print("\nAccenture SAP CO Management Accounting Mumbai matches:")
for m in accenture_matches:
    print(" ", m)

conn.close()
