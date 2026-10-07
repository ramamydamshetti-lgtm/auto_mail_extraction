import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from ui.app import UI_CONFIG
from ui.db import fetch_all_records

records = fetch_all_records(UI_CONFIG)
print(f"Total UI records available: {len(records)}")

target_ids = ["203483-1", "209160-1"]
for tid in target_ids:
    print(f"\n=================== SEARCH FOR CLIENT REQ ID: {tid} ===================")
    matches = [r for r in records if r.get('payload', {}).get('client_jd_id') == tid or r.get('req_id') == tid]
    print(f"Found {len(matches)} matching UI records for {tid}:")
    for r in matches:
        p = r.get('payload', {})
        print(f"  Internal ID: {r.get('req_id')} | Client Req ID: {p.get('client_jd_id')} | Title: {p.get('job_title')} | Status: {p.get('job_status')} | Client: {p.get('requirement_from')}")
