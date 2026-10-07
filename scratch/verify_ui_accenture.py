import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.db import fetch_all_records, get_requirement
from ui.app import UI_CONFIG

records = fetch_all_records(UI_CONFIG)
print(f"Total unique deduplicated records: {len(records)}")

accenture_titles = [r['payload'].get('job_title') for r in records if r['payload'].get('requirement_from') == 'Accenture']
print(f"Accenture job titles ({len(accenture_titles)} total):")
for t in accenture_titles[:15]:
    print(f"  - {t}")

req_209160 = get_requirement(UI_CONFIG, '209160-1')
if req_209160:
    print("\n209160-1 Requirement:")
    print(f"  Req ID: {req_209160.get('req_id')}")
    print(f"  Client JD ID: {req_209160.get('client_jd_id')}")
    print(f"  Job Title: {req_209160.get('payload', {}).get('job_title')}")
    print(f"  Client: {req_209160.get('payload', {}).get('requirement_from')}")
    print(f"  Location: {req_209160.get('payload', {}).get('location')}")

# Check if any "Accenture Requirement" remains
generic = [r for r in records if str(r['payload'].get('job_title')).lower() == 'accenture requirement']
print(f"\nRemaining 'Accenture Requirement' records: {len(generic)}")
