import sys
sys.path.insert(0, '.')
from ui.app import load_config
from ui.db import fetch_all_records

cfg = load_config()
records = fetch_all_records(cfg)

print(f"Total fetched records: {len(records)}")
for i, rec in enumerate(records[:10]):
    req_id = rec.get("req_id")
    client_jd = rec.get("client_jd_id")
    payload = rec.get("payload", {})
    client_name = payload.get("requirement_from")
    title = payload.get("job_title")
    print(f"Rec {i+1}: req_id={req_id} | client_jd_id={client_jd} | client_name={client_name} | title={title[:30] if title else ''}")
