import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()

print(f"Total rows: {len(rows)}")

false_duplicates = []
accenture_req_rows = []

for r in rows:
    p = json.loads(r['payload_json'])
    cid = str(r['client_jd_id'] or '')
    pid = str(p.get('client_jd_id') or '')
    title = str(p.get('job_title') or '')
    
    if title.lower() == 'accenture requirement' or 'requirement' == title.lower():
        accenture_req_rows.append((r['job_id'], cid, pid, title, p.get('subject')))
        
    if any(k in cid.lower() for k in ['job description', 'comments for supplier', 'description:']):
        false_duplicates.append((r['job_id'], cid, pid, title))
    elif any(k in pid.lower() for k in ['job description', 'comments for supplier', 'description:']):
        false_duplicates.append((r['job_id'], cid, pid, title))

print(f"\nRows with generic/placeholder title ('Accenture Requirement'): {len(accenture_req_rows)}")
for a in accenture_req_rows:
    print(f"  {a[0]} | DB CID: {a[1]} | Payload CID: {a[2]} | Title: {a[3]} | Subj: {a[4]}")

print(f"\nRows with false client_jd_id ('Job Description:' / 'Comments for Suppliers:'): {len(false_duplicates)}")
for f in false_duplicates:
    print(f"  {f[0]} | DB CID: {f[1]} | Payload CID: {f[2]} | Title: {f[3]}")

conn.close()
