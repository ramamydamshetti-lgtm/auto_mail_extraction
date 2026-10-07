import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
req_ids = ['2026/10/05-011', '2026/09/11-001', '2026/09/29-024', '2026/09/07-023']

for rid in req_ids:
    row = c.execute('SELECT payload_json FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ?', (rid, rid)).fetchone()
    p = json.loads(row[0]) if row else {}
    print(f"\n{'='*30} {rid} {'='*30}")
    print("Subject:", p.get('subject'))
    print("From:", p.get('from'))
    print("Client:", p.get('requirement_from'))
    print("Job Title:", p.get('job_title'))
    print("Mandatory Skills in DB:", p.get('mandatory_skills'))
    print("Skills in DB:", p.get('skills'))
    print("\n--- BODY TEXT ---")
    lines = (p.get('bodyText') or '').splitlines()
    for i, l in enumerate(lines[:35]):
        print(f"{i+1:02d}: {l}")
    if len(lines) > 35:
        print(f"... ({len(lines)-35} more lines)")
conn.close()
