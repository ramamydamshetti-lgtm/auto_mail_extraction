import sys
sys.path.insert(0, ".")
import sqlite3
from ui.db import fetch_all_records, update_status_in_db, get_requirement

config = {'db_paths': ['data/metaforge_requirements.db', 'data/processed_messages.db']}

# Check top record
recs_before = fetch_all_records(config)
top_rec = recs_before[0]
req_id = top_rec["req_id"]
cjd = top_rec.get("client_jd_id")
target = cjd or req_id
print(f"Testing status update on: {req_id} (target={target})")
print(f"Current status: {top_rec.get('job_status')}")

# Update status to 'hold'
success = update_status_in_db(config, target, "hold", changed_by="TEST_SCRIPT")
print(f"Update to hold success: {success}")

# Re-fetch records
recs_after = fetch_all_records(config)
updated_top = next((r for r in recs_after if r["req_id"] == req_id), None)
print(f"Updated status: {updated_top.get('job_status')}")
print(f"Same req_id count in records: {len([r for r in recs_after if r['req_id'] == req_id])}")
print(f"Total count before: {len(recs_before)}, Total count after: {len(recs_after)}")

# Revert back to open
update_status_in_db(config, target, "open", changed_by="TEST_SCRIPT")
recs_revert = fetch_all_records(config)
reverted_top = next((r for r in recs_revert if r["req_id"] == req_id), None)
print(f"Reverted status: {reverted_top.get('job_status')}")
