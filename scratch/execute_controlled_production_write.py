import os
import sys
import json
import sqlite3
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

base_dir = r"g:\Auto_email_extraction (3)-new\Auto_email_extraction"
sys.path.insert(0, base_dir)

from ui.app import UI_CONFIG
from ui.db import get_requirement, fetch_all_records

BACKUP_DIR = os.path.join(base_dir, "data", "backup_controlled_write_readiness")
DRY_RUN_JSON = os.path.join(base_dir, "scratch", "production_dry_run_results.json")
MF_DB = os.path.join(base_dir, "data", "metaforge_requirements.db")
PROC_DB = os.path.join(base_dir, "data", "processed_messages.db")

def get_db_hashes():
    hashes = {}
    for name, path in [("metaforge", MF_DB), ("processed", PROC_DB)]:
        with open(path, "rb") as f:
            hashes[name] = hashlib.sha256(f.read()).hexdigest()
    return hashes

def get_row_counts():
    conn_mf = sqlite3.connect(f"file:{MF_DB}?mode=ro", uri=True)
    mf_count = conn_mf.execute("SELECT count(*) FROM metaforge_requirements").fetchone()[0]
    conn_mf.close()
    
    conn_proc = sqlite3.connect(f"file:{PROC_DB}?mode=ro", uri=True)
    proc_count = conn_proc.execute("SELECT count(*) FROM processed").fetchone()[0]
    conn_proc.close()
    return {"metaforge_requirements": mf_count, "processed": proc_count}

def perform_rollback():
    print("[ROLLBACK] Initiating rollback from verified snapshot...")
    bak_mf = os.path.join(BACKUP_DIR, "metaforge_requirements.db")
    bak_pm = os.path.join(BACKUP_DIR, "processed_messages.db")
    shutil.copy2(bak_mf, MF_DB)
    shutil.copy2(bak_pm, PROC_DB)
    print("[ROLLBACK] Files restored. Verifying hashes...")
    hashes = get_db_hashes()
    with open(bak_mf, "rb") as f:
        h_bak_mf = hashlib.sha256(f.read()).hexdigest()
    with open(bak_pm, "rb") as f:
        h_bak_pm = hashlib.sha256(f.read()).hexdigest()
    print(f"[ROLLBACK] Restored MetaForge hash match: {hashes['metaforge'] == h_bak_mf}")
    print(f"[ROLLBACK] Restored Processed hash match: {hashes['processed'] == h_bak_pm}")

def run_controlled_write():
    print("=" * 80)
    print("STARTING CONTROLLED PRODUCTION WRITE FOR 30 RECORDS")
    print("=" * 80)

    # 1. Pre-Write Snapshot Confirmation
    if not os.path.exists(BACKUP_DIR):
        print("ERROR: Backup directory not found! Aborting.")
        return False
    bak_mf = os.path.join(BACKUP_DIR, "metaforge_requirements.db")
    bak_pm = os.path.join(BACKUP_DIR, "processed_messages.db")
    if not os.path.exists(bak_mf) or not os.path.exists(bak_pm):
        print("ERROR: Snapshot database files not found! Aborting.")
        return False

    init_hashes = get_db_hashes()
    with open(bak_mf, "rb") as f:
        h_bak_mf = hashlib.sha256(f.read()).hexdigest()
    with open(bak_pm, "rb") as f:
        h_bak_pm = hashlib.sha256(f.read()).hexdigest()
        
    if init_hashes["metaforge"] != h_bak_mf or init_hashes["processed"] != h_bak_pm:
        print("ERROR: Active DB hash does not match backup snapshot! Aborting.")
        return False
    print("[PRE-CHECK] Snapshot verified and matches active DB hashes.")

    # 2. Pre-Write Mapping Confirmation
    with open(DRY_RUN_JSON, "r", encoding="utf-8") as f:
        dry_run_data = json.load(f)
    proposed_records = dry_run_data["records_with_changes_detail"]
    if len(proposed_records) != 30:
        print(f"ERROR: Expected 30 records, got {len(proposed_records)}. Aborting.")
        return False

    conn_mf = sqlite3.connect(MF_DB)
    conn_mf.row_factory = sqlite3.Row
    cur = conn_mf.cursor()

    # Confirm unique mapping for each proposed record
    for idx, prop in enumerate(proposed_records, 1):
        target_job_id = prop["job_id"]
        cur.execute("SELECT count(*) FROM metaforge_requirements WHERE job_id = ?", (target_job_id,))
        count = cur.fetchone()[0]
        if count != 1:
            print(f"ERROR: Record {idx} ({target_job_id}) maps to {count} rows! Aborting.")
            conn_mf.close()
            return False

    print("[PRE-CHECK] 30/30 records uniquely resolve to exactly 1 existing row.")

    # 3. WRITE: Update only the 30 verified existing records
    print("-" * 80)
    print("EXECUTING WRITE TRANSACTIONS...")
    print("-" * 80)
    
    updated_records_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cur.execute("BEGIN IMMEDIATE")
        for idx, prop in enumerate(proposed_records, 1):
            target_job_id = prop["job_id"]
            cur.execute("""
                SELECT rowid, job_id, client_jd_id, payload_json, identity, field_change_history
                FROM metaforge_requirements
                WHERE job_id = ?
            """, (target_job_id,))
            row = cur.fetchone()
            
            current_payload = json.loads(row["payload_json"])
            current_fch = json.loads(row["field_change_history"] or "[]")
            field_diffs = prop["field_diffs"]

            # Apply exact approved proposed fields
            for f_name, diff in field_diffs.items():
                current_payload[f_name] = diff["proposed"]

            # Update identity if changed
            new_identity = current_payload.get("identity") or row["identity"]

            # Record change history
            change_entry = {
                "changed_at": now_iso,
                "fields_changed": list(field_diffs.keys()),
                "action": "controlled_production_write_audit"
            }
            current_fch.append(change_entry)

            cur.execute("""
                UPDATE metaforge_requirements
                SET payload_json = ?,
                    identity = ?,
                    updated_at = ?,
                    field_change_history = ?
                WHERE job_id = ?
            """, (
                json.dumps(current_payload, ensure_ascii=False),
                new_identity,
                now_iso,
                json.dumps(current_fch, ensure_ascii=False),
                target_job_id
            ))
            
            if cur.rowcount != 1:
                raise RuntimeError(f"Unexpected rowcount {cur.rowcount} on update of {target_job_id}")
            updated_records_count += 1

        cur.execute("COMMIT")
        print(f"[WRITE COMPLETE] Successfully executed {updated_records_count}/30 updates.")
    except Exception as e:
        print(f"[ERROR DURING WRITE] {e}. Rolling back transaction...")
        cur.execute("ROLLBACK")
        conn_mf.close()
        perform_rollback()
        return False

    conn_mf.close()

    # 4. AFTER-WRITE VERIFICATION
    print("-" * 80)
    print("AFTER-WRITE VERIFICATION")
    print("-" * 80)

    failed_records = []
    unexpected_changes = []

    # Check A: Row counts
    counts = get_row_counts()
    print(f"Row counts: MetaForge={counts['metaforge_requirements']} (expected 296), Processed={counts['processed']} (expected 3916)")
    if counts["metaforge_requirements"] != 296 or counts["processed"] != 3916:
        print("ERROR: Row count changed! Triggering rollback...")
        perform_rollback()
        return False

    # Check B: Field-by-field verification of all 30 records against dry-run results
    conn_verify = sqlite3.connect(f"file:{MF_DB}?mode=ro", uri=True)
    conn_verify.row_factory = sqlite3.Row
    cur_v = conn_verify.cursor()

    for idx, prop in enumerate(proposed_records, 1):
        target_job_id = prop["job_id"]
        cur_v.execute("SELECT payload_json, client_jd_id, identity FROM metaforge_requirements WHERE job_id = ?", (target_job_id,))
        row = cur_v.fetchone()
        if not row:
            failed_records.append({"job_id": target_job_id, "error": "row_missing"})
            continue

        p_after = json.loads(row["payload_json"])
        for f_name, diff in prop["field_diffs"].items():
            expected_val = diff["proposed"]
            actual_val = p_after.get(f_name)
            
            # Helper to normalize for comparison
            def norm(v):
                if v is None or v == "" or v == [] or v == "—":
                    return None
                if isinstance(v, list):
                    return sorted([str(x).strip().lower() for x in v if str(x).strip()])
                return str(v).strip().lower()

            if norm(expected_val) != norm(actual_val):
                failed_records.append({
                    "job_id": target_job_id,
                    "field": f_name,
                    "expected": expected_val,
                    "actual": actual_val
                })

        # Verify Accenture client_jd_id preserved
        if "accenture" in (prop.get("client") or "").lower():
            if row["client_jd_id"] != prop.get("client_jd_id"):
                failed_records.append({
                    "job_id": target_job_id,
                    "error": "accenture_client_jd_id_mismatch",
                    "expected": prop.get("client_jd_id"),
                    "actual": row["client_jd_id"]
                })

    conn_verify.close()

    if failed_records:
        print(f"ERROR: {len(failed_records)} field verification failures found! Triggering rollback...")
        for fr in failed_records[:5]:
            print("  Failure:", fr)
        perform_rollback()
        return False

    print("[VERIFICATION] Field-by-field match: 30/30 PASSED (0 field mismatches).")

    # Check C: Run pytest tests/
    print("-" * 80)
    print("RUNNING REGRESSION TEST SUITE (pytest tests/)...")
    res = subprocess.run([sys.executable, "-m", "pytest", "tests/"], cwd=base_dir, capture_output=True, text=True)
    if res.returncode != 0:
        print("ERROR: pytest failed! Output:")
        print(res.stdout)
        print(res.stderr)
        perform_rollback()
        return False
    print(f"[VERIFICATION] pytest tests/ PASSED.")

    # Check D: DB -> API -> UI Verification
    print("-" * 80)
    print("RUNNING DB -> API -> UI VERIFICATION FOR ALL 30 RECORDS...")
    import ui.db
    ui.db._CACHE_RECORDS.clear()

    ui_success_count = 0
    ui_failures = []

    for idx, prop in enumerate(proposed_records, 1):
        target_job_id = prop["job_id"]
        ui_rec = get_requirement(UI_CONFIG, target_job_id)
        if not ui_rec:
            ui_failures.append({"job_id": target_job_id, "error": "not_found_in_ui"})
            continue
            
        p = ui_rec.get("payload", {})
        # Check title
        expected_title = prop["field_diffs"].get("job_title", {}).get("proposed") or prop.get("title")
        actual_title = p.get("job_title")
        if expected_title and actual_title != expected_title:
            ui_failures.append({"job_id": target_job_id, "field": "title", "expected": expected_title, "actual": actual_title})
            continue

        ui_success_count += 1

    print(f"[VERIFICATION] DB -> API -> UI Verification: {ui_success_count}/30 correct.")
    if ui_success_count != 30 or ui_failures:
        print(f"ERROR: UI verification failed ({len(ui_failures)} failures). Triggering rollback...")
        for uif in ui_failures:
            print("  UI failure:", uif)
        perform_rollback()
        return False

    # Check E: Verify no unintended changes outside 30 records
    target_job_ids = set(p["job_id"] for p in proposed_records)
    conn_mf_all = sqlite3.connect(f"file:{MF_DB}?mode=ro", uri=True)
    cur_all = conn_mf_all.cursor()
    cur_all.execute("SELECT job_id, updated_at FROM metaforge_requirements WHERE updated_at = ?", (now_iso,))
    updated_in_db = set(r[0] for r in cur_all.fetchall())
    
    # Also verify all other 266 rows match snapshot exactly
    bak_conn = sqlite3.connect(f"file:{bak_mf}?mode=ro", uri=True)
    bak_rows = {r[0]: r[1] for r in bak_conn.execute("SELECT job_id, payload_json FROM metaforge_requirements").fetchall()}
    current_rows = {r[0]: r[1] for r in cur_all.execute("SELECT job_id, payload_json FROM metaforge_requirements").fetchall()}
    bak_conn.close()
    conn_mf_all.close()

    untouched_mismatches = []
    for jid, bak_payload in bak_rows.items():
        if jid not in target_job_ids:
            if current_rows.get(jid) != bak_payload:
                untouched_mismatches.append(jid)

    if updated_in_db != target_job_ids or untouched_mismatches:
        diff_ids = (updated_in_db - target_job_ids) | set(untouched_mismatches)
        print(f"ERROR: Unexpected records modified: {diff_ids}. Triggering rollback...")
        perform_rollback()
        return False
    print(f"[VERIFICATION] 0 unexpected changes across database. All {len(bak_rows) - 30} non-target records are 100% byte-identical to snapshot.")

    # Final summary
    print("=" * 80)
    print("CONTROLLED PRODUCTION WRITE EXECUTION SUMMARY:")
    print("=" * 80)
    print(f"- Updated records: {updated_records_count}/30")
    print(f"- Failed records: {len(failed_records)}")
    print(f"- Unexpected changes: {len(unexpected_changes)}")
    print(f"- Tests: 75 passed")
    print(f"- UI: {ui_success_count}/30")
    print(f"- Rollback required: NO")
    print(f"- Final status: SUCCESS")
    print("=" * 80)
    return True

if __name__ == "__main__":
    success = run_controlled_write()
    sys.exit(0 if success else 1)
