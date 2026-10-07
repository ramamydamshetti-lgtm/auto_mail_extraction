import sqlite3
import json

conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()

c_mr.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE job_id LIKE '%027%' OR payload_json LIKE '%027%'")
rows = c_mr.fetchall()

print(f"Found {len(rows)} matching rows in metaforge_requirements.db:\n")
for jid, pjson, ca in rows:
    p = json.loads(pjson)
    print(f"=== JOB ID: {jid} ===")
    print(f"  client_jd_id  : {p.get('client_jd_id')}")
    print(f"  req_id        : {p.get('req_id')}")
    print(f"  job_title     : {p.get('job_title')}")
    print(f"  requirement_from: {p.get('requirement_from')}")
    print(f"  _has_req_id   : {p.get('_has_req_id')}")
    prov = p.get('_provenance') or {}
    print(f"  _provenance   : {prov}")
    print()

conn_mr.close()
