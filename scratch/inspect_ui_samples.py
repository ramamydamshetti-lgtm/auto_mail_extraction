import sys
sys.path.insert(0, ".")
import json
from ui.app import app, load_config
from ui.db import fetch_all_records

client = app.test_client()

# 1. Main Dashboard
resp = client.get("/")
print("Dashboard HTTP status:", resp.status_code)
html = resp.get_data(as_text=True)

# 2. Query UI records directly
cfg = load_config()
records = fetch_all_records(cfg)
print(f"Total requirements displayed in UI: {len(records)}")

# Pick sample requirements across different clients:
# - Accenture (e.g., SAP or Pega)
# - LTTS (e.g., Lead Power System Engineer or Hardware)
# - KPMG (e.g., Data Scientist)
# - A requirement with 'hold' or 'closed' status / field history

samples = {
    "Accenture_SAP": None,
    "Accenture_Pega": None,
    "LTTS": None,
    "KPMG": None,
    "Hold_Status": None,
}

for r in records:
    c = str(r.get("client") or (r.get("payload") or {}).get("requirement_from") or "").lower()
    title = str(r.get("job_title") or (r.get("payload") or {}).get("job_title") or "").lower()
    st = str(r.get("job_status") or (r.get("payload") or {}).get("job_status") or "").lower()
    
    if "accenture" in c and "pega" in title and not samples["Accenture_Pega"]:
        samples["Accenture_Pega"] = r
    elif "accenture" in c and "sap" in title and not samples["Accenture_SAP"]:
        samples["Accenture_SAP"] = r
    elif "ltts" in c and not samples["LTTS"]:
        samples["LTTS"] = r
    elif ("kpmg" in c or "data scientist" in title) and not samples["KPMG"]:
        samples["KPMG"] = r
    elif st in ("hold", "closed") and not samples["Hold_Status"]:
        samples["Hold_Status"] = r

for name, r in samples.items():
    if not r:
        continue
    p = r.get("payload") or {}
    job_id = r.get("fmt_id") or r.get("raw_req_id") or p.get("job_id")
    cjd = r.get("client_jd_id") or p.get("client_jd_id")
    
    print("\n" + "=" * 70)
    print(f"SAMPLE CATEGORY: {name}")
    print(f"Job ID: {job_id} | Client JD ID: {cjd} | Client: {p.get('requirement_from') or r.get('client')}")
    print(f"Job Title: {p.get('job_title') or r.get('job_title')}")
    print(f"Status: {r.get('job_status') or p.get('job_status')}")
    print(f"Location: {p.get('location')} | Work Mode: {p.get('work_mode')}")
    print(f"Experience: {p.get('overall_experience')} (Level: {p.get('experience_level')})")
    print(f"Mandatory Skills: {p.get('mandatory_skills')}")
    print(f"Skills: {p.get('skills')}")
    print(f"Notice Period: {p.get('notice_period')}")
    print(f"Budget: Yearly={p.get('yearly_budget')}, Monthly={p.get('monthly_budget')}, Text={p.get('budget_text')}")
    print(f"Positions: {p.get('number_of_positions')}")
    print(f"Field History: {r.get('field_change_history') or p.get('field_change_history')}")
    print(f"Provenance: {p.get('_provenance')}")
    
    # Check detail page rendering
    if job_id:
        req_resp = client.get(f"/requirement/{job_id}")
        print(f"Detail Page GET /requirement/{job_id}: {req_resp.status_code}")
