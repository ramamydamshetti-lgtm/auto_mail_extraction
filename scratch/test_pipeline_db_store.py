import sys
import os
import json
import sqlite3
sys.path.insert(0, os.path.abspath("."))

from processed_store import ProcessedStore

print("=== VERIFYING DATABASE STORAGE PIPELINE ===")

db_path = "data/metaforge_requirements.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Ensure table exists
cur.execute("""
CREATE TABLE IF NOT EXISTS metaforge_requirements (
    job_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")
conn.commit()

# Insert a sample extracted Outlook requirement to demonstrate pipeline storage
sample_job_id = "ACC-2026-09-29-001"
sample_payload = {
    "job_id": sample_job_id,
    "client_jd_id": sample_job_id,
    "demand_received_date": "2026-09-29",
    "internal_poc": "hiring@iexcel.co.in",
    "requirement_from": "Accenture",
    "client_lead_poc": "anusha.k@iexcel.co.in",
    "client_poc": "rkarnam@metaforgeit.com",
    "job_title": "Senior SAP S/4HANA Cloud Consultant (Automated Outlook Extract)",
    "job_status": "Open",
    "closed_date": "N/A",
    "type_of_demand": "Single",
    "priority": "High",
    "number_of_positions": 3,
    "experience_level": "Senior",
    "employment_type": "Full-time",
    "budget_currency": "INR",
    "monthly_budget": "200000",
    "work_mode": "Hybrid",
    "location": "Bangalore / Remote",
    "overall_experience": "6-10 years",
    "notice_period": "Immediate",
    "mandatory_skills": "SAP S/4HANA Cloud; ABAP Restful Programming; SAP Fiori",
    "skills": "SAP BTP; HANA Cloud",
    "submissions_count": 0
}

cur.execute(
    "INSERT OR REPLACE INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
    (sample_job_id, json.dumps(sample_payload), "2026-09-29T16:00:00Z")
)
conn.commit()
conn.close()

print(f"Successfully stored extracted requirement '{sample_job_id}' into SQLite DB: {db_path}")

# Verify UI database reader
from ui.db import fetch_all_records
cfg = json.load(open("ui/config.json"))
records = fetch_all_records(cfg)

matching = [r for r in records if r["req_id"] == sample_job_id]
print(f"Total UI records fetched: {len(records)}")
if matching:
    print(f"SUCCESS: UI successfully read stored requirement '{sample_job_id}'!")
    print("  Title:", matching[0]["payload"].get("job_title"))
    print("  Client:", matching[0]["payload"].get("requirement_from"))
    print("  Skills:", matching[0]["payload"].get("mandatory_skills"))
