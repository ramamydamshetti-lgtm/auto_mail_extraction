"""
Data Repair Script for Auto_email_extraction (Rules A1, A2, A3, N8).

Supports:
  --dry-run (default): Simulates all repairs, prints diffs, and changes nothing.
  --apply: Applies all repairs to data/*.db. (Ensures backups exist first).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from requirement_comparator import build_requirement_profile, compare_requirements
from requirement_identity import clean_client_jd_id, compute_requirement_identity, normalize_client_key

DATA_DIR = PROJECT_ROOT / "data"
PROC_DB = DATA_DIR / "processed_messages.db"
MF_DB = DATA_DIR / "metaforge_requirements.db"
SEQ_DB = DATA_DIR / "metaforge_sequences.db"
BACKUP_DIR = DATA_DIR / "backup_20261001"
BACKUP_JSON = PROJECT_ROOT / "metaforge_consolidated_2026-09-30.json"

OVERWRITTEN_CLIENT_IDS = [
    "198381-1", "198377-1", "188662-1", "200134-1", "200968-1", "203502-1",
    "203421-1", "203190-1", "203484-1", "204307-1", "203146-1", "204241-1",
    "204237-1", "204617-1", "205118-1", "206291-1", "206678-1", "186544-1",
    "207725-1", "187291-1", "187643-1", "187686-1", "187653-1", "187663-1",
    "187654-1", "187657-1", "187664-1", "188848-1", "187655-1", "187651-1",
    "187638-1", "187648-1", "188603-1", "209160-1",
]


def create_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for f in os.listdir(DATA_DIR):
        if f.endswith(".db"):
            src = DATA_DIR / f
            dst = BACKUP_DIR / f
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
    print(f"[BACKUP] Databases backed up in: {BACKUP_DIR}")


def run_repair(apply_changes: bool = False):
    mode_str = "APPLYING CHANGES" if apply_changes else "DRY RUN (READ-ONLY)"
    print("=" * 80)
    print(f"DATA REPAIR: {mode_str}")
    print("=" * 80)

    if apply_changes:
        create_backups()

    # Load 09-30 backup for pristine states
    backup_dict = {}
    if BACKUP_JSON.exists():
        with open(BACKUP_JSON, "r", encoding="utf-8") as f:
            for item in json.load(f):
                cid = item.get("client_jd_id")
                if cid:
                    p_orig = {}
                    if item.get("payload_json"):
                        try:
                            p_orig = json.loads(item["payload_json"])
                        except Exception:
                            p_orig = {}
                    backup_dict[cid] = {
                        "row": item,
                        "payload": p_orig,
                    }

    conn_mf = sqlite3.connect(f"file:{MF_DB}" + ("" if apply_changes else "?mode=ro"), uri=True)
    conn_proc = sqlite3.connect(f"file:{PROC_DB}" + ("" if apply_changes else "?mode=ro"), uri=True)

    # -------------------------------------------------------------------------
    # PART 1: RESTORE THE 34 OVERWRITTEN ROWS (A1)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PART 1: RESTORING 34 OVERWRITTEN REQUIREMENTS TO ORIGINAL SEPTEMBER STATE")
    print("-" * 80)
    print(f"{'Client ID':<12} | {'Job ID':<16} | {'Restored Date':<14} | {'Restored Time':<24} | {'Recovery Source'}")
    print("-" * 80)

    restored_count = 0
    for cjd in OVERWRITTEN_CLIENT_IDS:
        row = conn_mf.execute(
            "SELECT job_id, payload_json, created_at, updated_at, field_change_history FROM metaforge_requirements WHERE client_jd_id = ?",
            (cjd,),
        ).fetchone()
        if not row:
            continue

        job_id, p_str, created_at, updated_at, fch_str = row
        cur_payload = json.loads(p_str)
        cur_fch = json.loads(fch_str or "[]")

        orig_state = backup_dict.get(cjd)
        source = "metaforge_consolidated_2026-09-30.json"

        # Determine pristine values
        if orig_state:
            p_orig = orig_state["payload"]
            r_orig = orig_state["row"]
            res_demand_date = p_orig.get("demand_received_date")
            res_received_time = p_orig.get("receivedDateTime")
            res_updated_at = r_orig.get("updated_at") or r_orig.get("created_at") or created_at
            restored_payload = dict(p_orig)
        else:
            # Fallback: recover from job_id and field_change_history
            source = "field_change_history / job_id (approximate)"
            res_demand_date = job_id.split("-")[0].replace("/", "-")
            res_received_time = f"{res_demand_date}T00:00:00Z"
            res_updated_at = created_at
            restored_payload = dict(cur_payload)
            restored_payload["demand_received_date"] = res_demand_date
            restored_payload["receivedDateTime"] = res_received_time

        # Detect diff of changed keys (A1)
        row_changed_keys = []
        for k in set(cur_payload.keys()) | set(restored_payload.keys()):
            if cur_payload.get(k) != restored_payload.get(k):
                row_changed_keys.append(k)

        # Remove the 2026-10-01 overwrite entry from field_change_history
        cleaned_fch = [h for h in cur_fch if "2026-10-01" not in h.get("changed_at", "")]

        diff_summary = f"{len(row_changed_keys)} keys changed"
        print(f"{cjd:<12} | {job_id:<16} | {str(res_demand_date):<14} | {str(res_received_time):<24} | {source} ({diff_summary})")

        if apply_changes:
            conn_mf.execute(
                """UPDATE metaforge_requirements
                   SET payload_json = ?, updated_at = ?, field_change_history = ?
                   WHERE client_jd_id = ?""",
                (json.dumps(restored_payload, ensure_ascii=False), res_updated_at, json.dumps(cleaned_fch, ensure_ascii=False), cjd),
            )
            # Also update client_requirements in proc_db if present
            conn_proc.execute(
                """UPDATE client_requirements
                   SET payload_json = ?, updated_at = ?, field_change_history = ?
                   WHERE client_jd_id = ?""",
                (json.dumps(restored_payload, ensure_ascii=False), res_updated_at, json.dumps(cleaned_fch, ensure_ascii=False), cjd),
            )

        restored_count += 1

    print(f"Total requirements restored: {restored_count}")

    # -------------------------------------------------------------------------
    # PART 2: RENUMBER 200964-1 & SET TODAY'S COUNTER (A2)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PART 2: RENUMBER TODAY'S NEW REQUIREMENT (200964-1) & FIX SEQUENCE COUNTER")
    print("-" * 80)

    row_new = conn_mf.execute(
        "SELECT job_id, payload_json FROM metaforge_requirements WHERE client_jd_id = '200964-1'"
    ).fetchone()

    if row_new:
        old_jid, p_str = row_new
        p_new = json.loads(p_str)
        new_jid = "2026/10/01-001"
        p_new["job_id"] = new_jid
        p_new["former_job_id"] = old_jid

        print(f"Renumbering 200964-1: {old_jid} -> {new_jid} (former_job_id recorded: {old_jid})")
        print("Sequence counter for 2026-10-01: set value to 1 (Next allocated will be 2026/10/01-002)")

        if apply_changes:
            # Update metaforge_requirements
            conn_mf.execute(
                """UPDATE metaforge_requirements
                   SET job_id = ?, payload_json = ?
                   WHERE client_jd_id = '200964-1'""",
                (new_jid, json.dumps(p_new, ensure_ascii=False)),
            )
            # Update sequence in mf_sequences in both databases
            for c_seq in [conn_mf, conn_proc]:
                try:
                    c_seq.execute(
                        "INSERT INTO mf_sequences (name, value) VALUES ('job:2026/10/01', 1) "
                        "ON CONFLICT(name) DO UPDATE SET value = 1"
                    )
                except Exception:
                    pass

            if SEQ_DB.exists():
                try:
                    c_s = sqlite3.connect(str(SEQ_DB))
                    c_s.execute(
                        "INSERT INTO mf_sequences (name, value) VALUES ('job:2026/10/01', 1) "
                        "ON CONFLICT(name) DO UPDATE SET value = 1"
                    )
                    c_s.commit()
                    c_s.close()
                except Exception:
                    pass

            # Update client_requirements and requirement_memory
            conn_proc.execute(
                "UPDATE client_requirements SET payload_json = ? WHERE client_jd_id = '200964-1'",
                (json.dumps(p_new, ensure_ascii=False),),
            )
            conn_proc.execute(
                "UPDATE requirement_memory SET payload_json = ? WHERE payload_json LIKE '%200964-1%'",
                (json.dumps(p_new, ensure_ascii=False),),
            )
    else:
        print("Requirement 200964-1 not found in metaforge_requirements.")

    # -------------------------------------------------------------------------
    # PART 3: SEED REQUIREMENT_IDENTITY & ARCHIVE DUPLICATES (A3)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PART 3: SEEDING requirement_identity & ARCHIVING DUPLICATES")
    print("-" * 80)

    # Fetch all rows from metaforge_requirements oldest first
    all_mf = conn_mf.execute(
        "SELECT job_id, client_jd_id, created_at, updated_at, payload_json FROM metaforge_requirements ORDER BY created_at ASC, job_id ASC"
    ).fetchall()

    unique_identities = []
    duplicates_to_archive = []

    for jid, cjd_raw, cat, uat, pstr in all_mf:
        # Note: If this is 200964-1, use its new job_id 2026/10/01-001
        eff_jid = "2026/10/01-001" if cjd_raw == "200964-1" else jid
        p = json.loads(pstr)
        cjd = clean_client_jd_id(cjd_raw or p.get("client_jd_id"))
        client = normalize_client_key(p.get("requirement_from") or p.get("client_key") or "unknown")
        body_text = str(p.get("bodyText") or p.get("body") or "")
        prof = build_requirement_profile(p, body_text=body_text)

        ident = compute_requirement_identity(
            client=client,
            client_jd_id=cjd,
            job_title=p.get("job_title"),
            location=p.get("location"),
            experience=p.get("overall_experience") or p.get("experience_level"),
            mandatory_skills=p.get("mandatory_skills"),
        )

        is_dup = False
        matched_jid = None
        deciding_rule = None
        score_val = 0.0

        if cjd:
            for ui in unique_identities:
                if ui["client"] == client and ui["client_jd_id"] == cjd:
                    is_dup = True
                    matched_jid = ui["job_id"]
                    deciding_rule = f"SAME_CLIENT_JD_ID ({cjd})"
                    score_val = 1.0
                    break

        if not is_dup:
            for ui in unique_identities:
                dec, score, rule = compare_requirements(prof, ui["profile"])
                if dec == "DUPLICATE":
                    is_dup = True
                    matched_jid = ui["job_id"]
                    deciding_rule = rule
                    score_val = score
                    break

        if is_dup:
            duplicates_to_archive.append({
                "job_id": eff_jid,
                "client_jd_id": cjd,
                "client": client,
                "identity": ident,
                "original_job_id": matched_jid,
                "deciding_rule": deciding_rule,
                "similarity_score": score_val,
                "payload_json": pstr,
                "created_at": cat,
            })
        else:
            unique_identities.append({
                "job_id": eff_jid,
                "client": client,
                "client_jd_id": cjd,
                "city": prof.get("city"),
                "identity": ident,
                "profile": prof,
                "created_at": cat,
            })

    print(f"Total rows in metaforge_requirements: {len(all_mf)}")
    print(f"Unique records to seed in requirement_identity: {len(unique_identities)}")
    print(f"Duplicate records to archive in duplicates_archive: {len(duplicates_to_archive)}")

    print("\nDuplicate Archive Candidates:")
    for d in duplicates_to_archive:
        print(f"  Move {d['job_id']:<16} (client_jd_id={str(d['client_jd_id']):<10}) -> DUPLICATE of {d['original_job_id']:<16} via {d['deciding_rule']} (score={d['similarity_score']:.2f})")

    if apply_changes:
        # Create requirement_identity and duplicates_archive tables in proc_db
        conn_proc.execute(
            """CREATE TABLE IF NOT EXISTS requirement_identity (
                identity TEXT PRIMARY KEY,
                client TEXT NOT NULL,
                client_jd_id TEXT,
                city TEXT,
                state TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                times_seen INTEGER NOT NULL DEFAULT 1,
                original_record_ref TEXT,
                last_graph_id TEXT,
                profile_json TEXT,
                text_fingerprint TEXT
            )"""
        )
        conn_proc.execute(
            """CREATE TABLE IF NOT EXISTS duplicates_archive (
                archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                client_jd_id TEXT,
                client TEXT,
                identity TEXT,
                original_job_id TEXT,
                deciding_rule TEXT,
                similarity_score REAL,
                payload_json TEXT,
                archived_at TEXT
            )"""
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        # Insert into requirement_identity
        conn_proc.execute("DELETE FROM requirement_identity")
        for ui in unique_identities:
            conn_proc.execute(
                """INSERT OR REPLACE INTO requirement_identity
                   (identity, client, client_jd_id, city, state, first_seen, last_seen, times_seen, original_record_ref, profile_json, text_fingerprint)
                   VALUES (?, ?, ?, ?, 'stored', ?, ?, 1, ?, ?, ?)""",
                (
                    ui["identity"],
                    ui["client"],
                    ui["client_jd_id"],
                    ui["city"],
                    ui["created_at"],
                    ui["created_at"],
                    ui["job_id"],
                    json.dumps(ui["profile"]),
                    ui["profile"].get("text_fingerprint") or "",
                ),
            )

        # Archive duplicates into duplicates_archive and delete duplicates from metaforge_requirements
        for da in duplicates_to_archive:
            conn_proc.execute(
                """INSERT INTO duplicates_archive
                   (job_id, client_jd_id, client, identity, original_job_id, deciding_rule, similarity_score, payload_json, archived_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    da["job_id"],
                    da["client_jd_id"],
                    da["client"],
                    da["identity"],
                    da["original_job_id"],
                    da["deciding_rule"],
                    da["similarity_score"],
                    da["payload_json"],
                    now_iso,
                ),
            )
            # Remove duplicate from metaforge_requirements to keep single store clean
            conn_mf.execute("DELETE FROM metaforge_requirements WHERE job_id = ?", (da["job_id"],))

        conn_mf.commit()
        conn_proc.commit()
        print("\n[SUCCESS] All repairs applied successfully to data/*.db!")
    else:
        print("\n[DRY RUN COMPLETE] No database records were modified.")

    conn_mf.close()
    conn_proc.close()


def main():
    parser = argparse.ArgumentParser(description="Repair and re-seed requirements data.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to data/*.db (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run mode (does not write changes)")
    args = parser.parse_args()

    run_repair(apply_changes=args.apply)


if __name__ == "__main__":
    main()
