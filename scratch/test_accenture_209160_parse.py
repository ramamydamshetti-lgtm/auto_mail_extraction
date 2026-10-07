import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from config import Settings
from requirement_parser import (
    parse_requirements_from_email,
    extract_client_jd_id_from_text,
    extract_req_id_table_requirements
)
from intake_gates import is_status_or_tracker_report

settings = Settings.from_env()

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

subject = msg.get('subject', '')
body_obj = msg.get('body', {}) or {}
body = body_obj.get('content', '')

print("Subject:", subject)
print("Is status or tracker report?", is_status_or_tracker_report(subject, body))
print("Extracted client_jd_id using extract_client_jd_id_from_text:", extract_client_jd_id_from_text(subject, body))

table_reqs = extract_req_id_table_requirements(subject, body)
print(f"\nextract_req_id_table_requirements count: {len(table_reqs)}")
for idx, r in enumerate(table_reqs):
    print(f" Table req #{idx+1}: job_title={r.job_title}, client_jd_id={r.client_jd_id}, job_status={r.job_status}")

parsed = parse_requirements_from_email(
    subject=subject,
    body=body,
    settings=settings,
    from_email='anusha.k@iexcel.co.in'
)
print("\n--- parse_requirements_from_email result ---")
print("Processing note:", parsed.processing_note)
print("Confidence:", parsed.overall_confidence)
print(f"Total requirements extracted: {len(parsed.requirements)}")
for idx, item in enumerate(parsed.requirements):
    print(f"\nItem #{idx+1}:")
    print("  Job Title:", item.job_title)
    print("  Client JD ID:", item.client_jd_id)
    print("  Status:", item.job_status)
    print("  Requirement From:", item.requirement_from)
    print("  Skills:", item.skills)
