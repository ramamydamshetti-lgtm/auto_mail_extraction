import json
import sqlite3
import re
from ui.app import app, UI_CONFIG
from ui.db import _open_ro_connection, fetch_all_records, get_requirement

print("================ ACCEPTANCE TEST RUN ================")

# 1. Real Data Row Count
records = fetch_all_records(UI_CONFIG)
print(f"\n[ACCEPTANCE 1] Total real records loaded in UI: {len(records)}")
assert len(records) > 0, "No records found!"

# 2. Autofill one real Req ID and print JSON verbatim
sample_id = records[0]["req_id"]
print(f"\n[ACCEPTANCE 2] Autofilling real Req ID '{sample_id}' via API...")
with app.test_client() as client:
    res = client.get(f"/api/requirement/{sample_id}")
    print(f"Status Code: {res.status_code}")
    print("Verbatim JSON returned:")
    print(json.dumps(res.get_json(), indent=2))

# 3. Unknown ID returns not found
print("\n[ACCEPTANCE 3] Testing unknown ID 'UNKNOWN-REQ-ID-99999'...")
with app.test_client() as client:
    res = client.get("/api/requirement/UNKNOWN-REQ-ID-99999")
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.get_json()}")

# 5. Write attempt through UI connection fails
print("\n[ACCEPTANCE 5] Testing write attempt through UI read-only connection...")
ro_conn = _open_ro_connection(UI_CONFIG["db_paths"][0])
try:
    ro_conn.execute("INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES ('HACK', '{}', '2026-01-01')")
    print("ERROR: Write succeeded unexpectedly!")
except sqlite3.OperationalError as e:
    print(f"CONFIRMED: Write attempt failed with expected error: {e}")
finally:
    ro_conn.close()

print("\n================ ACCEPTANCE RUN COMPLETE ================")
