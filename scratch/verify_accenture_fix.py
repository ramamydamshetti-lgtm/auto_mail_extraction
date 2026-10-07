import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))
from config import Settings
from requirement_parser import parse_requirements_from_email

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

target_209160 = [r for r in parsed.requirements if r.req_id == '209160-1']
print(f"Found target req_id '209160-1': {len(target_209160)}")

if target_209160:
    item = target_209160[0]
    print("\n=== EXTRACTED RECORD FOR ACCENTURE 209160-1 ===")
    print("  req_id:", item.req_id)
    print("  job_title:", item.job_title)
    print("  raw_status:", item.raw_status)
    print("  location:", item.location)
    print("  experience:", item.experience)
    print("  mandatory_skills:", item.mandatory_skills)
    print("  client_name:", item.client_name)

print("\n--- ALL EXTRACTED REQ IDs (FIRST 15) ---")
for idx, r in enumerate(parsed.requirements[:15]):
    print(f"  Item #{idx+1:2d}: req_id={str(r.req_id):<12} | title={str(r.job_title):<45} | status={r.raw_status}")
