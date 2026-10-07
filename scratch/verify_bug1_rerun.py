import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import sqlite3, json
from config import Settings
from requirement_parser import parse_requirements_from_email
from historical_autofill import autofill_from_history
from processed_store import ProcessedStore
from boilerplate_learner import validate_skills

settings = Settings.from_env()

con = sqlite3.connect("data/metaforge_requirements.db")
con.row_factory = sqlite3.Row

print("=== RE-RUNNING BUG 1 RECORDS ===")

for jid in ["2026/09/08-005", "2026/09/30-007"]:
    r = con.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ?", (jid,)).fetchone()
    payload = json.loads(r["payload_json"])
    
    source_text = payload.get("bodyText") or payload.get("body") or payload.get("raw_body") or payload.get("source_text") or ""
    subj = payload.get("subject") or payload.get("email_subject") or ""
    sender = payload.get("sender_email") or payload.get("from") or ""
    cjd = r["client_jd_id"]
    client_name = payload.get("requirement_from") or payload.get("client") or "Accenture"
    
    print(f"\n--- {jid} ({payload.get('job_title')}) ---")
    print(f"Old Mandatory Skills: {payload.get('mandatory_skills')}")
    print(f"Old Skills: {payload.get('skills')}")
    
    # Parse fresh from source text
    parse_res = parse_requirements_from_email(
        subject=subj,
        body=source_text,
        settings=settings,
        from_email=sender,
    )
    
    matched_req = None
    if parse_res.requirements:
        for req in parse_res.requirements:
            if req.req_id == cjd or req.job_title == payload.get("job_title"):
                matched_req = req
                break
        if not matched_req:
            matched_req = parse_res.requirements[0]
            
    if matched_req:
        new_mand = matched_req.mandatory_skills
        new_soft = matched_req.soft_skills
    else:
        new_mand = None
        new_soft = None
        
    # Validate with boilerplate / template cleaner
    new_mand = validate_skills(new_mand, client=client_name)
    new_soft = validate_skills(new_soft, client=client_name)
    
    # Simulate autofill_from_history
    payload["mandatory_skills"] = new_mand
    payload["skills"] = new_soft
    with ProcessedStore(settings.processed_db) as store:
        payload = autofill_from_history(payload, store)
        
    print(f"New Mandatory Skills: {payload.get('mandatory_skills')}")
    print(f"New Skills: {payload.get('skills')}")
    
    # Check for any SAP contamination
    all_s = " ".join(str(s) for s in (payload.get("mandatory_skills") or []) + (payload.get("skills") or [])).lower()
    has_sap = "sap" in all_s
    print(f"Contains SAP contamination: {has_sap}")
