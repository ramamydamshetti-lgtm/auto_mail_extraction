import sqlite3
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
query = """
    SELECT id, requirement_from, job_title_norm, source_graph_id, payload_json, created_at 
    FROM requirement_memory 
    WHERE payload_json LIKE '%Data Scientist%'
"""
rows = conn.execute(query).fetchall()

print(f"Total matching memory rows: {len(rows)}")
for r in rows:
    p = json.loads(r[4])
    print(f"Memory ID {r[0]}:")
    print(f"  Created: {r[5]} | From: {r[1]} | TitleNorm: {r[2]}")
    print(f"  GID: {r[3]}")
    print(f"  Job Title: {p.get('job_title')}")
    print(f"  Location: {p.get('location')}")
    print(f"  Exp: {p.get('overall_experience')} / {p.get('experience')}")
    print(f"  Notice: {p.get('notice_period')}")
    print(f"  Status: {p.get('job_status')}")
    print(f"  CJD: {p.get('client_jd_id')}")
    print(f"  Subject: {p.get('email_subject')}")
    print(f"  Confidence: {p.get('confidence')}")
    print(f"  Provenance: {p.get('_provenance')}")
    print("-" * 50)

# Also check client_requirements and metaforge_requirements
print("\n=== In client_requirements ===")
for r in conn.execute("SELECT client_jd_id, requirement_from, created_at, updated_at, payload_json FROM client_requirements WHERE payload_json LIKE '%Data Scientist%'").fetchall():
    p = json.loads(r[4])
    print(f"CJD: {r[0]} | From: {r[1]} | Created: {r[2]} | Updated: {r[3]}")
    print(f"  Title: {p.get('job_title')} | Loc: {p.get('location')} | Exp: {p.get('overall_experience')} | Notice: {p.get('notice_period')}")

conn.close()

conn_mf = sqlite3.connect('data/metaforge_requirements.db')
print("\n=== In metaforge_requirements ===")
for r in conn_mf.execute("SELECT job_id, client_jd_id, created_at, updated_at, payload_json FROM metaforge_requirements WHERE payload_json LIKE '%Data Scientist%'").fetchall():
    p = json.loads(r[4])
    print(f"Job ID: {r[0]} | CJD: {r[1]} | Created: {r[2]} | Updated: {r[3]}")
    print(f"  Title: {p.get('job_title')} | Loc: {p.get('location')} | Exp: {p.get('overall_experience')} | Notice: {p.get('notice_period')}")
conn_mf.close()
