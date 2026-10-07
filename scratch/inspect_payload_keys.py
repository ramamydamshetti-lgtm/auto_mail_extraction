import sys
import os
import json
sys.path.insert(0, os.path.abspath("."))
from ui.db import fetch_all_records

cfg = json.load(open("ui/config.json"))
recs = fetch_all_records(cfg)

print(f"Total records: {len(recs)}")

for i in range(10):
    r = recs[i]
    p = r.get("payload", {})
    print(f"\n--- Record {i+1}: {r.get('req_id')} ---")
    print("  source_db:", r.get("source_db"))
    print("  created_at:", r.get("created_at"))
    print("  Payload keys:", list(p.keys()))
    print("  requirement_from:", p.get("requirement_from"))
    print("  client_lead_poc:", p.get("client_lead_poc"))
    print("  client_poc:", p.get("client_poc"))
    print("  client_contact:", p.get("client_contact") or p.get("client_contact_number") or p.get("contact_number") or p.get("phone"))
    print("  job_title:", p.get("job_title"))
    print("  job_status:", p.get("job_status"))
    print("  priority:", p.get("priority"))
    print("  demand_received_date:", p.get("demand_received_date"))
    print("  location:", p.get("location"))
    print("  experience_level:", p.get("experience_level") or p.get("overall_experience"))
    print("  employment_type:", p.get("employment_type"))
    print("  mandatory_skills:", p.get("mandatory_skills"))
    print("  skills:", p.get("skills"))
