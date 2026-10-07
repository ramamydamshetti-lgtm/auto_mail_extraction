import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

print("Subject:", msg.get('subject'))
print("From:", msg.get('from'))
body_obj = msg.get('body', {}) or {}
content = body_obj.get('content', '')
print("Body Content Length:", len(content))
print("--- BODY CONTENT SNIPPET ---")
print(content[:2000])

from requirement_parser import extract_and_map
extracted, confidence = extract_and_map(msg)
print("\n--- EXTRACTED RESULTS ---")
print("Confidence:", confidence)
if isinstance(extracted, list):
    for idx, item in enumerate(extracted):
        print(f"\nItem #{idx+1}:")
        print("  Job ID:", item.get('job_id'))
        print("  Client JD ID:", item.get('client_jd_id'))
        print("  Requirement From:", item.get('requirement_from'))
        print("  Job Title:", item.get('job_title'))
        print("  Status:", item.get('job_status'))
else:
    print("  Job ID:", extracted.get('job_id'))
    print("  Client JD ID:", extracted.get('client_jd_id'))
    print("  Requirement From:", extracted.get('requirement_from'))
    print("  Job Title:", extracted.get('job_title'))
    print("  Status:", extracted.get('job_status'))
