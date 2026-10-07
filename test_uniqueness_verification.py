import sqlite3
import json
import copy
from pathlib import Path

from config import Settings
from processed_store import ProcessedStore
from requirement_comparator import build_requirement_profile, compare_requirements
from metaforge_api import _sqlite_upsert
from ui.app import load_config
from ui.db import fetch_all_records

db_path = "data/metaforge_requirements.db"
pm_path = "data/processed_messages.db"

store = ProcessedStore(Path(pm_path))
settings = Settings.from_env()

conn_mf = sqlite3.connect(db_path)
conn_mf.row_factory = sqlite3.Row

# Get baseline counts
initial_db_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
cfg = load_config()
initial_ui_count = len(fetch_all_records(cfg))

print(f"=== BASELINE ===")
print(f"DB count: {initial_db_count} | UI count: {initial_ui_count}")
assert initial_db_count == initial_ui_count, "DB and UI counts must match initially"

# =========================================================================
# TEST 1: Old requirement repeated (Accenture Request-ID 200964-1) -> 0 new records
# =========================================================================
print("\n=== TEST 1: Old requirement repeated (Accenture 200964-1) ===")
# Fetch existing record for 200964-1
acc_existing = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = '200964-1'").fetchone()
assert acc_existing is not None, "200964-1 must exist in DB"
acc_payload = json.loads(acc_existing["payload_json"])

# Incoming repeated email with same payload
repeated_payload = copy.deepcopy(acc_payload)
repeated_payload["graphMessageId"] = "AAMk_TEST_REPEATED_ACCENTURE_DIGEST_EMAIL="

# Step 4 check: find_requirement_duplicate
prof = build_requirement_profile(repeated_payload)
decision, matched_cand, score, rule = store.find_requirement_duplicate(prof)
print(f"find_requirement_duplicate: decision={decision}, score={score}, rule={rule}")
assert decision == "DUPLICATE", f"Repeated requirement must be detected as DUPLICATE, got {decision}"

# Check _sqlite_upsert directly as well:
upserted_id = _sqlite_upsert(repeated_payload, db_path)
print(f"Upsert returned job_id: {upserted_id} (canonical: {acc_existing['job_id']})")
assert upserted_id == acc_existing["job_id"], "Upsert must return existing job_id without creating a new record"

current_db_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
print(f"DB count after repeated requirement: {current_db_count} (change: {current_db_count - initial_db_count})")
assert current_db_count == initial_db_count, "Zero new records must be created for repeated requirement"

# =========================================================================
# TEST 2: Same requirement repeated without client ID (LTTS 2026/09/20-004) -> 0 new records
# =========================================================================
print("\n=== TEST 2: Same requirement in repeated email without client ID (LTTS 2026/09/20-004) ===")
ltts_existing = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = '2026/09/20-004'").fetchone()
assert ltts_existing is not None, "2026/09/20-004 must exist in DB"
ltts_payload = json.loads(ltts_existing["payload_json"])

repeated_ltts = copy.deepcopy(ltts_payload)
repeated_ltts.pop("job_id", None)
repeated_ltts["graphMessageId"] = "AAMk_TEST_REPEATED_LTTS_OCT_EMAIL="

prof_ltts = build_requirement_profile(repeated_ltts)
dec_ltts, match_ltts, score_ltts, rule_ltts = store.find_requirement_duplicate(prof_ltts)
print(f"find_requirement_duplicate: decision={dec_ltts}, score={score_ltts}, rule={rule_ltts}")
assert dec_ltts == "DUPLICATE", f"Repeated LTTS requirement must be DUPLICATE, got {dec_ltts}"

upserted_ltts_id = _sqlite_upsert(repeated_ltts, db_path)
print(f"Upsert returned job_id: {upserted_ltts_id} (canonical: {ltts_existing['job_id']})")
assert upserted_ltts_id == ltts_existing["job_id"], "Must update same job_id without creating new record"

current_db_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
print(f"DB count after repeated LTTS requirement: {current_db_count} (change: {current_db_count - initial_db_count})")
assert current_db_count == initial_db_count, "Zero new records must be created for repeated LTTS requirement"

# =========================================================================
# TEST 3: Client changes existing requirement -> same ID updated
# =========================================================================
print("\n=== TEST 3: Client changes existing requirement -> same ID updated ===")
change_payload = copy.deepcopy(acc_payload)
change_payload["job_status"] = "hold"
change_payload["number_of_positions"] = 5
change_payload["graphMessageId"] = "AAMk_TEST_ACCENTURE_STATUS_HOLD_EMAIL="

upserted_change_id = _sqlite_upsert(change_payload, db_path)
print(f"Upsert returned job_id: {upserted_change_id} (canonical: {acc_existing['job_id']})")
assert upserted_change_id == acc_existing["job_id"], "Must update same ID"

updated_row = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (acc_existing["job_id"],)).fetchone()
p_updated = json.loads(updated_row["payload_json"])
hist = json.loads(updated_row["field_change_history"] or "[]")
print(f"Updated status: {p_updated.get('job_status')}, positions: {p_updated.get('number_of_positions')}")
assert p_updated.get("job_status") == "hold", "Status must be updated to hold"
assert p_updated.get("number_of_positions") == 5, "Positions must be updated to 5"
assert len(hist) > 0, "field_change_history must record the change"
print(f"Latest change in history: {hist[-1]}")

current_db_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
assert current_db_count == initial_db_count, "No new requirement record created on client change"

# Revert test change back to original so production data remains intact
revert_payload = copy.deepcopy(acc_payload)
_sqlite_upsert(revert_payload, db_path)

# =========================================================================
# TEST 4: Verification of 1:1 alignment between DB and UI
# =========================================================================
print("\n=== TEST 4: Verification of 1:1 alignment between DB and UI ===")
final_db_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
ui_records = fetch_all_records(cfg)
final_ui_count = len(ui_records)

print(f"Unique requirements in DB: {final_db_count}")
print(f"Unique requirements in UI: {final_ui_count}")
assert final_db_count == final_ui_count, f"DB ({final_db_count}) and UI ({final_ui_count}) counts MUST match 1:1"

# Verify all IDs are unique in both DB and UI
db_ids = [r[0] for r in conn_mf.execute("SELECT job_id FROM metaforge_requirements").fetchall()]
ui_ids = [r["req_id"] for r in ui_records]

assert len(db_ids) == len(set(db_ids)), "Duplicate job_ids found in DB!"
assert len(ui_ids) == len(set(ui_ids)), "Duplicate req_ids found in UI!"
assert set(db_ids) == set(ui_ids), "DB IDs and UI IDs do not match 1:1!"

print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
conn_mf.close()
store.close()
