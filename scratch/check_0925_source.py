import sys
sys.path.insert(0, ".")
from ui.db import fetch_all_records

config = {'db_paths': ['data/metaforge_requirements.db', 'data/processed_messages.db']}
recs = fetch_all_records(config)
r_0925 = [r for r in recs if "2026/09/25" in str(r.get("req_id") or "")]
print(f"Total 09/25 records in UI: {len(r_0925)}")
for r in r_0925:
    print(r.get("req_id"), r.get("source_db"), r.get("source_table"), r.get("raw_req_id"), r.get("first_arrival_at"), r.get("payload",{}).get("client_jd_id"))
