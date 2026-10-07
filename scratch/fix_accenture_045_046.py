import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row

# Check 045 and 046
rows = conn.execute("SELECT * FROM metaforge_requirements WHERE job_id IN ('2026/09/30-045', '2026/09/30-046')").fetchall()
print(f"Found {len(rows)} rows to fix in metaforge_requirements.db")

for r in rows:
    p = json.loads(r['payload_json'])
    print(f"Old job_id={r['job_id']}, client_jd_id={r['client_jd_id']}, title={p.get('job_title')}")
    p['client_jd_id'] = '209160-1'
    p['job_title'] = 'SAP FSCM Treasury and Risk Management (TRM)'
    p['location'] = 'Bangalore(BDC7)'
    p['overall_experience'] = '7.5 Yrs'
    p['mandatory_skills'] = ['SAP FSCM Treasury and Risk Management (TRM)']
    p['priority'] = 'HIGH'
    
    conn.execute(
        "UPDATE metaforge_requirements SET client_jd_id = ?, payload_json = ? WHERE job_id = ?",
        ('209160-1', json.dumps(p, ensure_ascii=False), r['job_id'])
    )

conn.commit()
print("Updated rows in metaforge_requirements.db!")

# Also let's check if 209160-1 deduplication works
conn.close()
