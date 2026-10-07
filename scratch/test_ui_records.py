import json
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from ui.app import UI_CONFIG
from ui.db import fetch_all_records

records = fetch_all_records(UI_CONFIG)
print(f"Total UI records returned by fetch_all_records: {len(records)}")

print("\n--- FIRST 20 UI RECORDS ---")
for idx, r in enumerate(records[:20]):
    job_id = str(r.get('job_id') or r.get('id') or '')
    client_id = str(r.get('client_jd_id') or '')
    client = str(r.get('requirement_from') or '')
    title = str(r.get('job_title') or '')
    status = str(r.get('job_status') or '')
    print(f"Record #{idx+1:2d}: job_id={job_id:<18} | client_id={client_id:<12} | client={client:<10} | title={title:<40} | status={status}")
