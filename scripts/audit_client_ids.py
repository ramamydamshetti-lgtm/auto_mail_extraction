"""
Audit and Repair Client IDs (C1 - C5).
Dry run first; apply with --apply.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from client_identity_validator import is_genuine_client_id
from requirement_identity import compute_requirement_identity, normalize_client_key


def audit_client_ids(db_path: str = "data/metaforge_requirements.db", apply: bool = False) -> None:
    if not os.path.exists(db_path):
        print(f"[ERROR] Database {db_path} not found.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(metaforge_requirements)")
    cols = {c[1] for c in cur.fetchall()}
    has_identity_col = "identity" in cols

    cur.execute("SELECT job_id, client_jd_id, payload_json" + (", identity" if has_identity_col else "") + " FROM metaforge_requirements")
    rows = cur.fetchall()

    broken_rows = []
    for r in rows:
        job_id = r["job_id"]
        cjd_col = r["client_jd_id"]
        p = json.loads(r["payload_json"]) if r["payload_json"] else {}
        cjd_payload = p.get("client_jd_id")
        client_name = p.get("requirement_from") or p.get("client_name") or p.get("client_key")
        body_text = p.get("bodyText") or p.get("body") or p.get("email_body") or ""
        subject = p.get("subject") or p.get("email_subject") or p.get("source_subject") or ""
        
        # Test candidate ID
        cand_id = cjd_col or cjd_payload
        if cand_id:
            is_val, clean_id, reason = is_genuine_client_id(
                client_name,
                cand_id,
                context={"text": body_text, "subject": subject, "job_title": p.get("job_title"), "location": str(p.get("location"))},
            )
            if not is_val:
                # Recompute content identity
                new_ident = compute_requirement_identity(
                    client=client_name,
                    client_jd_id=None,
                    job_title=p.get("job_title"),
                    location=p.get("location"),
                    experience=p.get("overall_experience") or p.get("experience_level"),
                    mandatory_skills=p.get("mandatory_skills"),
                )
                broken_rows.append({
                    "job_id": job_id,
                    "client_name": client_name,
                    "rejected_client_id": cand_id,
                    "reason": reason,
                    "old_identity": (r["identity"] if has_identity_col else p.get("identity")),
                    "new_identity": new_ident,
                    "title": p.get("job_title"),
                    "payload": p,
                })

    print("=" * 100)
    mode_str = "APPLYING REPAIRS" if apply else "DRY RUN (READ-ONLY)"
    print(f"AUDIT CLIENT IDS REPORT: {mode_str}")
    print("=" * 100)
    print(f"Total rows inspected: {len(rows)}")
    print(f"Rows with invalid client ID: {len(broken_rows)}")
    print("-" * 100)

    if broken_rows:
        print(f"{'Job ID':<18} | {'Client':<12} | {'Rejected Client ID':<20} | {'Reason':<25} | {'Job Title':<25}")
        print("-" * 100)
        for b in broken_rows:
            print(f"{b['job_id']:<18} | {str(b['client_name'])[:12]:<12} | {str(b['rejected_client_id']):<20} | {str(b['reason']):<25} | {str(b['title'])[:25]}")

    # Check duplicate decisions in processed_messages.db made only because of a rejected ID
    proc_db = "data/processed_messages.db"
    suspect_duplicates = []
    if os.path.exists(proc_db):
        pconn = sqlite3.connect(proc_db)
        pconn.row_factory = sqlite3.Row
        pcur = pconn.cursor()
        try:
            pcur.execute("SELECT job_id, original_job_id, client, deciding_rule, payload_json FROM duplicates_archive")
            dups = pcur.fetchall()
            for d in dups:
                d_reason = str(d["deciding_rule"] or "")
                dp = json.loads(d["payload_json"]) if d["payload_json"] else {}
                cand_cid = dp.get("client_jd_id") or dp.get("req_id")
                c_name = d["client"] or dp.get("requirement_from")
                if cand_cid:
                    is_val, _, r_reason = is_genuine_client_id(c_name, cand_cid)
                    if not is_val:
                        suspect_duplicates.append({
                            "incoming_id": d["job_id"],
                            "existing_ref": d["original_job_id"],
                            "client": c_name,
                            "rejected_id": cand_cid,
                            "rejection_reason": r_reason,
                            "email_subject": dp.get("subject") or dp.get("email_subject") or dp.get("source_subject"),
                            "graph_message_id": dp.get("graphMessageId") or dp.get("graph_id"),
                        })
        except Exception as exc:
            print("Note on duplicates archive check:", exc)

    print("\n" + "=" * 100)
    print("DUPLICATE DECISIONS CHECK (DROPPED SOLELY DUE TO REJECTED IDs)")
    print("=" * 100)
    print(f"Suspect dropped duplicates: {len(suspect_duplicates)}")
    if suspect_duplicates:
        print(f"{'Incoming ID':<20} | {'Existing Ref':<20} | {'Client':<10} | {'Rejected ID':<18} | {'Subject / Graph ID'}")
        print("-" * 100)
        for sd in suspect_duplicates:
            print(f"{str(sd['incoming_id']):<20} | {str(sd['existing_ref']):<20} | {str(sd['client']):<10} | {str(sd['rejected_id']):<18} | {str(sd['email_subject'])[:30]} ({sd['graph_message_id']})")
    else:
        print("None. No requirements were dropped due to a rejected ID.")

    if apply and broken_rows:
        backup_dir = "data/backup_client_ids_apply"
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(db_path, os.path.join(backup_dir, os.path.basename(db_path)))
        print(f"\n[BACKUP] Created safety backup at {backup_dir}")

        for b in broken_rows:
            p = b["payload"]
            p["former_client_id"] = b["rejected_client_id"]
            p["client_jd_id"] = None
            p["identity"] = b["new_identity"]
            if has_identity_col:
                conn.execute(
                    """UPDATE metaforge_requirements
                       SET client_jd_id = NULL,
                           identity = ?,
                           payload_json = ?
                       WHERE job_id = ?""",
                    (b["new_identity"], json.dumps(p, ensure_ascii=False), b["job_id"]),
                )
            else:
                conn.execute(
                    """UPDATE metaforge_requirements
                       SET client_jd_id = NULL,
                           payload_json = ?
                       WHERE job_id = ?""",
                    (json.dumps(p, ensure_ascii=False), b["job_id"]),
                )
        conn.commit()
        print(f"[SUCCESS] Applied client ID corrections to {len(broken_rows)} rows!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and repair client IDs (C5).")
    parser.add_argument("--apply", action="store_true", help="Apply repairs to the database.")
    args = parser.parse_args()
    audit_client_ids(apply=args.apply)
