import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from config import Settings
from requirement_parser import parse_requirements_from_email, extract_req_id_table_requirements

settings = Settings.from_env()

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

subject = msg.get('subject', '')
body_obj = msg.get('body', {}) or {}
body = body_obj.get('content', '')

parsed = parse_requirements_from_email(
    subject=subject,
    body=body,
    settings=settings,
    from_email='anusha.k@iexcel.co.in'
)

print(f"Total requirements extracted by parser: {len(parsed.requirements)}")

matching_209160 = []
for idx, r in enumerate(parsed.requirements):
    req_id = r.req_id
    title = r.job_title
    status = r.raw_status
    if '209160' in str(req_id) or '209160' in str(r):
        matching_209160.append((idx, r))
        print(f"MATCH AT ITEM #{idx+1}: req_id={req_id} | title={title} | raw_status={status}")

print(f"\nTotal items matching 209160: {len(matching_209160)}")

print("\n--- Listing ALL 57 extracted req_ids ---")
for idx, r in enumerate(parsed.requirements):
    print(f"Item #{idx+1:2d}: req_id={str(r.req_id):<15} | title={str(r.job_title):<35} | status={r.raw_status}")
