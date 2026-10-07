import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ui.app import UI_CONFIG
from ui.db import fetch_all_records, get_requirement

records = fetch_all_records(UI_CONFIG)
print("Searching for 2026/09/30-044...")
for i, r in enumerate(records):
    rid = r.get("req_id")
    raw = r.get("raw_req_id")
    cjd = r.get("client_jd_id")
    if "044" in str(rid) or "044" in str(raw) or "044" in str(cjd):
        p = r.get("payload", {})
        print(f"Match index={i}: req_id={rid}, raw={raw}, cjd={cjd}, client={p.get('requirement_from')}, title={p.get('job_title')}")

print("\nCalling get_requirement(UI_CONFIG, '2026/09/30-044'):")
res = get_requirement(UI_CONFIG, "2026/09/30-044")
if res:
    print(f"Returned: req_id={res.get('req_id')}, raw={res.get('raw_req_id')}, cjd={res.get('client_jd_id')}, title={res.get('payload', {}).get('job_title')}")
else:
    print("None returned")
