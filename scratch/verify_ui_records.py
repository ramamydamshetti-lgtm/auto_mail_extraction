import sys
sys.path.insert(0, ".")
from ui.db import fetch_all_records

config = {'db_paths': ['data/metaforge_requirements.db', 'data/processed_messages.db']}
recs = fetch_all_records(config)
print(f"Total returned records: {len(recs)}")
print("--- TOP 35 RECORDS ---")
for i, r in enumerate(recs[:35], start=1):
    req_id = r.get("req_id")
    cjd = r.get("client_jd_id") or ""
    display = f"{req_id} ({cjd})" if cjd else req_id
    fa = r.get("first_arrival_at") or ""
    client = r.get("payload", {}).get("requirement_from", "")
    print(f"#{i:02d} | {display:30} | {fa:22} | {client}")
