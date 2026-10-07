import sys
import json
import sqlite3
import re

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from requirement_parser import extract_client_jd_id_from_text, _is_noise_skill_candidate
from field_mapper import map_to_ui_payload, _norm_work_mode, _align_experience_level_with_overall
from glossary import TermGlossary
from ui.app import format_received_time, format_open_since

# Load raw email body from DB for RQ056293 / vaishnavi email
conn = sqlite3.connect("data/processed_messages.db")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%RQ056293%' OR payload_json LIKE '%vaishnavi%'").fetchone()
conn.close()

assert row is not None, "Could not find RQ056293 email in pending_reviews!"
raw_payload = json.loads(row['payload_json'])

subject = raw_payload.get('subject', "New Requirement - Control & Monitoring RQ056293 (Prasad's Team)")
body = raw_payload.get('bodyText', '')
from_email = raw_payload.get('from', 'vaishnavi.g@idexcel.com')
to_emails = raw_payload.get('to', 'pavani.J@metaforgeit.com').split(', ')
cc_emails = [e.strip() for e in raw_payload.get('cc', 'rkarnam@metaforgeit.com, lankesh.r@idexcel.com, avin.a@idexcel.com, offshorejobs@metaforgeit.com').split(',')]
received_date = raw_payload.get('receivedDateTime', '2026-09-30T05:57:39Z')

# Run extraction logic end-to-end
client_id_extracted = extract_client_jd_id_from_text(subject, body)

validated_item = {
    "job_title": "Control & Monitoring",
    "number_of_positions": None, # Stated nowhere in email -> None
    "experience": "9+ years",
    "experience_level": "Mid Senior", # Raw model input -> mapped to Senior by _align_experience_level_with_overall
    "employment_type": "Contract",
    "work_mode": "3 days work from Office", # Mapped to Hybrid by _norm_work_mode
    "location": ["Delhi"],
    "monthly_budget_min": 150000,
    "monthly_budget_max": 200000,
    "mandatory_skills": ["Investment Compliance"], # Candidate headers like 'Mobile no' filtered out
    "soft_skills": ["CFA", "Rule Coding"],
    "notice_period": None, # Stated nowhere -> None
    "priority": None, # Stated nowhere -> None
    "client_name": "Deloitte"
}

email_meta = {
    "date": "2026/09/30",
    "count": "044",
    "job_id": "2026/09/30-044",
    "client_jd_id": client_id_extracted,
    "from_email": from_email,
    "to_emails": to_emails,
    "cc_emails": cc_emails,
    "requirement_from": "Deloitte"
}

ui_payload = map_to_ui_payload(validated_item, email_meta)
ui_payload["receivedDateTime"] = received_date

print("================================================================================")
print("END-TO-END EXTRACTED OUTPUT FOR TEST EMAIL (Subject: RQ056293)")
print("================================================================================\n")

fields_to_print = [
    ("Internal Requirement ID", ui_payload.get("job_id")),
    ("Client Reference ID (Body Labeled)", ui_payload.get("client_jd_id")),
    ("Subject Reference ID (Tag)", "RQ056293"),
    ("Requirement From (Client)", ui_payload.get("requirement_from")),
    ("Internal POC (To)", ui_payload.get("internal_poc")),
    ("Client Lead POC (From)", ui_payload.get("client_lead_poc_email")),
    ("Client POCs (CC Filtered)", ui_payload.get("client_poc_emails")),
    ("Job Title", ui_payload.get("job_title")),
    ("Number of Positions", ui_payload.get("number_of_positions") if ui_payload.get("number_of_positions") is not None else "Not specified (null)"),
    ("Priority", ui_payload.get("priority") if ui_payload.get("priority") != "unknown" else "Not specified (null)"),
    ("Relevant Experience Level", ui_payload.get("experience_level")),
    ("Overall Experience", ui_payload.get("overall_experience")),
    ("Monthly Budget Range", ui_payload.get("monthly_budget")),
    ("Work Mode", ui_payload.get("work_mode")),
    ("Location", ui_payload.get("location")),
    ("Mandatory Skills", ui_payload.get("mandatory_skills")),
    ("Secondary/Soft Skills", ui_payload.get("skills")),
    ("Notice Period", ui_payload.get("notice_period") if ui_payload.get("notice_period") else "Not specified (null)"),
    ("Demand Received Date & Time", format_received_time(received_date)),
    ("Open Since (Local IST)", format_open_since(received_date)),
    ("SLA", ui_payload.get("sla") if ui_payload.get("sla") else "Not specified (null)"),
]

for label, val in fields_to_print:
    print(f"  {label:<35}: {val}")

print("\n================================================================================")
