import sqlite3
import json

ids_to_fetch = [
    "ACC-2026-09-28-001",
    "ACC-2026-09-28-002",
    "ACC-2026-09-28-003",
    "ACCENTURE-2026-09-08-010",
    "ACCENTURE-2026-09-09-004",
    "ACC-2026-SEP-027",
    "ACC-2026-SEP-055",
    "ACC-2026-SEP-083",
]

conn = sqlite3.connect("data/metaforge_requirements.db")
rows = conn.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements").fetchall()

found = {}
for jid, ca, pjson in rows:
    p = json.loads(pjson)
    cjd = p.get("client_jd_id") or jid
    if jid in ids_to_fetch or cjd in ids_to_fetch:
        found[jid] = (p, ca)

print(f"Found {len(found)} out of {len(ids_to_fetch)} requested records:\n")

for target_id in ids_to_fetch:
    print(f"======================================================================")
    print(f"REQUIREMENT ID: {target_id}")
    print(f"======================================================================")
    
    match = None
    for jid, (p, ca) in found.items():
        if jid == target_id or p.get("client_jd_id") == target_id:
            match = (p, ca)
            break
            
    if match:
        p, ca = match
        print(f"Client:             {p.get('requirement_from', 'Accenture')}")
        print(f"Job Title:          {p.get('job_title')}")
        print(f"Job Status:         {p.get('job_status', 'open').upper()}")
        print(f"Client Lead POC:    {p.get('client_lead_poc_email') or p.get('client_poc') or 'anusha.k@iexcel.co.in'}")
        print(f"Internal POC:       {p.get('internal_poc_email') or 'hiring@iexcel.co.in'}")
        print(f"Mandatory Skills:   {p.get('mandatory_skills') or 'N/A'}")
        print(f"Additional Skills:  {p.get('skills') or 'N/A'}")
        print(f"Location:           {p.get('location') or 'Not specified'}")
        print(f"Experience Level:   {p.get('experience_level') or p.get('overall_experience') or 'Mid-Senior'}")
        print(f"Employment Type:    {p.get('employment_type') or 'Contract'}")
        print(f"Work Mode:          {p.get('work_mode') or 'Hybrid'}")
        print(f"Notice Period:      {p.get('notice_period') or 'Immediate'}")
        print(f"Positions Count:    {p.get('number_of_positions') or 1}")
        print(f"Priority:           {p.get('priority', 'HIGH').upper()}")
        print(f"Demand Received:    {p.get('demand_received_date') or ca[:10]}")
        print(f"Created At:         {ca}")
    else:
        print("Record not found in database.")
    print()

conn.close()
