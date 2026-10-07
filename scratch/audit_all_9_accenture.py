import sqlite3
import json

conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()

ids_9 = [
    "ACC-2026-09-29-001",
    "ACC-2026-09-28-001",
    "ACC-2026-09-28-002",
    "ACC-2026-09-28-003",
    "ACCENTURE-2026-09-08-010",
    "ACCENTURE-2026-09-09-004",
    "ACC-2026-SEP-027",
    "ACC-2026-SEP-055",
    "ACC-2026-SEP-083"
]

print("======================================================================")
print("COMPREHENSIVE AUDIT OF ALL 9 ACCENTURE REQUIREMENTS")
print("======================================================================")

found_records = {}
rows = c_mr.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements").fetchall()

for jid, pjson, ca in rows:
    p = json.loads(pjson)
    cjd = p.get("client_jd_id") or jid
    for target in ids_9:
        if jid == target or cjd == target:
            found_records[target] = (jid, cjd, p, ca)

print(f"Total Found in metaforge_requirements.db: {len(found_records)} / {len(ids_9)}\n")

for idx, req_id in enumerate(ids_9, 1):
    print("="*80)
    print(f"{idx}. TARGET ACCENTURE REQ ID: {req_id}")
    print("="*80)
    if req_id in found_records:
        jid, cjd, p, ca = found_records[req_id]
        print(f"  System Job ID     : {jid}")
        print(f"  Client JD ID       : {cjd}")
        print(f"  Job Title          : {p.get('job_title')}")
        print(f"  Job Status         : {p.get('job_status')}")
        print(f"  Demand Date        : {p.get('demand_received_date') or ca[:10]}")
        print(f"  Location           : {p.get('location')}")
        print(f"  Experience         : {p.get('overall_experience') or p.get('experience')}")
        print(f"  Positions          : {p.get('number_of_positions')}")
        print(f"  Client POC         : {p.get('client_lead_poc') or p.get('client_poc')}")
        print(f"  Mandatory Skills   : {p.get('mandatory_skills')}")
        print(f"  Monthly Budget     : {p.get('monthly_budget')}")
    else:
        print("  STATUS: NOT FOUND IN METAFORGE_REQUIREMENTS.DB")
    print()

conn_mr.close()
