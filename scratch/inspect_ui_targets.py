import sys
sys.path.insert(0, ".")
from ui.db import fetch_all_records
from ui.app import load_config
import json

cfg = load_config()
records = fetch_all_records(cfg)

targets = ["203528-1", "203529-1", "203514-1"]

for r in records:
    cjd = str(r.get("client_jd_id") or "")
    payload = r.get("payload") or {}
    title = str(payload.get("job_title") or "")
    
    # Check if target
    is_target = (cjd in targets or 
                 "pega marketing" in title.lower() or 
                 "angular" in str(payload).lower() or 
                 "data scientist" in title.lower() or 
                 "simulation" in str(payload.get("skills", [])).lower() or 
                 "simulation" in str(payload.get("mandatory_skills", [])).lower() or
                 "pss" in str(payload).lower())
    
    if is_target:
        print("="*70)
        print(f"ID: {r.get('fmt_id')} | CJD: {cjd} | Client: {payload.get('requirement_from')}")
        print(f"Title: {title}")
        print(f"Mandatory skills: {payload.get('mandatory_skills')}")
        print(f"Skills: {payload.get('skills')}")
        print(f"Location: {payload.get('location')} | Exp: {payload.get('overall_experience')} | Notice: {payload.get('notice_period')}")
        print(f"Budget: yearly={payload.get('yearly_budget')}, monthly={payload.get('monthly_budget')}, text={payload.get('budget_text')}")
        print(f"Status: {r.get('job_status') or payload.get('job_status')} | Provenance: {payload.get('_provenance')}")
