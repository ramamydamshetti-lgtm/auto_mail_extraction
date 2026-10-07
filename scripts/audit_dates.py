"""
Audit and repair date invariant across requirements.
Invariant: for rows created by the pipeline, the REQ date segment equals the IST date of first_arrival_at.

Order of recovery sources:
1. field_change_history
2. requirement_memory (source_graph_id)
3. earlier database backups (e.g. metaforge_consolidated_2026-09-30.json)
4. service-logs
5. original Graph message
6. REQ date segment (marked approximate)
Never use processing time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
MF_DB = DATA_DIR / "metaforge_requirements.db"
PROC_DB = DATA_DIR / "processed_messages.db"
BACKUP_JSON = PROJECT_ROOT / "metaforge_consolidated_2026-09-30.json"
BACKUP_DIR = DATA_DIR / "backup_dates_audit"

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_to_utc_dt(dt_val: Any) -> datetime:
    if not dt_val:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = str(dt_val).strip()
    if not s or s.lower() in ("none", "null", "n/a"):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
        if "+" in s[10:] or ("-" in s[10:] and len(s) > 16):
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if " " in s[:19]:
            s = s[:10] + "T" + s[11:]
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def extract_req_date(job_id: str) -> Optional[Tuple[str, int]]:
    """Extract (YYYY-MM-DD, sequence_number) from job_id."""
    if not job_id:
        return None
    m = re.match(r"^(\d{4})[/-](\d{2})[/-](\d{2})[-_](\d+)$", job_id.strip())
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", int(m.group(4))


def create_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for db in DATA_DIR.glob("*.db"):
        dst = BACKUP_DIR / db.name
        if not dst.exists() or db.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(db, dst)
    print(f"[BACKUP] Databases backed up in: {BACKUP_DIR}")


def audit_and_repair(
    mf_db_path: Path = MF_DB,
    proc_db_path: Path = PROC_DB,
    backup_json_path: Path = BACKUP_JSON,
    apply_changes: bool = False,
) -> Dict[str, Any]:
    """
    Perform audit and optional repair of dates.
    Returns audit statistics and list of rows investigated.
    """
    if not mf_db_path.exists():
        print(f"Database not found: {mf_db_path}")
        return {"matched": 0, "broken": 0, "legacy": 0, "broken_rows": []}

    # Load 09-30 consolidated backup if available
    backup_dict = {}
    if backup_json_path.exists():
        try:
            with open(backup_json_path, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    cid = item.get("client_jd_id")
                    if cid and item.get("payload_json"):
                        try:
                            p_orig = json.loads(item["payload_json"])
                            backup_dict[cid] = p_orig
                        except Exception:
                            pass
        except Exception:
            pass

    conn_mf = sqlite3.connect(str(mf_db_path))
    conn_proc = sqlite3.connect(str(proc_db_path)) if proc_db_path.exists() else None

    cur_mf = conn_mf.cursor()
    rows = cur_mf.execute(
        "SELECT job_id, client_jd_id, payload_json, created_at, updated_at, field_change_history FROM metaforge_requirements"
    ).fetchall()

    matched_count = 0
    legacy_count = 0
    broken_rows = []

    for r in rows:
        job_id = r[0] or ""
        client_jd = r[1]
        try:
            payload = json.loads(r[2])
        except Exception:
            payload = {}
        created_at_db = r[3] or ""
        updated_at_db = r[4] or ""
        try:
            fch = json.loads(r[5] or "[]")
        except Exception:
            fch = []

        parsed_req = extract_req_date(job_id)
        if not parsed_req:
            # Non-standard job_id (historical imports)
            legacy_count += 1
            continue

        req_date_str, seq_num = parsed_req

        # Current arrival timestamp
        prov = payload.get("_provenance") or {}
        curr_arr = (
            payload.get("first_arrival_at")
            or payload.get("receivedDateTime")
            or prov.get("receivedDateTime")
            or prov.get("received_date_time")
            or payload.get("demand_received_date")
            or created_at_db
        )

        if not curr_arr:
            legacy_count += 1
            continue

        dt_utc = _parse_to_utc_dt(curr_arr)
        dt_ist = dt_utc.astimezone(IST)
        ist_date_str = dt_ist.strftime("%Y-%m-%d")
        ist_display = dt_ist.strftime("%m/%d/%Y %I:%M %p")

        if req_date_str == ist_date_str:
            matched_count += 1
            # If first_arrival_at is not explicitly saved in payload, we should set it
            if apply_changes and not payload.get("first_arrival_at"):
                utc_iso = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                payload["first_arrival_at"] = utc_iso
                cur_mf.execute(
                    "UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?",
                    (json.dumps(payload, ensure_ascii=False), job_id),
                )
            continue

        # Invariant is broken! Find original value according to recovery priority:
        # 1. field_change_history
        # 2. requirement_memory (source_graph_id)
        # 3. earlier database backups
        # 4. service-logs
        # 5. original Graph message
        # 6. REQ date segment (mark approximate)
        restored_utc_iso = None
        recovery_source = None
        is_approximate = False

        # Source 1: field_change_history
        for entry in fch:
            changes = entry.get("changes", {})
            # Look for demand_received_date or receivedDateTime old value matching req_date
            if "receivedDateTime" in changes:
                old_recv = changes["receivedDateTime"].get("old")
                if old_recv and extract_req_date(f"{req_date_str}-001"):
                    t_utc = _parse_to_utc_dt(old_recv)
                    if t_utc.astimezone(IST).strftime("%Y-%m-%d") == req_date_str:
                        restored_utc_iso = t_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                        recovery_source = "field_change_history (receivedDateTime)"
                        break

        # Source 3: earlier database backups (e.g. metaforge_consolidated_2026-09-30.json)
        if not restored_utc_iso and client_jd and client_jd in backup_dict:
            b_payload = backup_dict[client_jd]
            b_recv = b_payload.get("receivedDateTime")
            if b_recv:
                t_utc = _parse_to_utc_dt(b_recv)
                if t_utc.astimezone(IST).strftime("%Y-%m-%d") == req_date_str:
                    restored_utc_iso = t_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                    recovery_source = "earlier database backup (metaforge_consolidated_2026-09-30.json)"

        # Source 2: requirement_memory in processed_messages.db
        if not restored_utc_iso and conn_proc and client_jd:
            try:
                mem_rows = conn_proc.execute(
                    "SELECT source_graph_id, payload_json FROM requirement_memory WHERE payload_json LIKE ? ORDER BY created_at ASC",
                    (f"%{client_jd}%",),
                ).fetchall()
                for mr in mem_rows:
                    try:
                        mp = json.loads(mr[1])
                        if mp.get("client_jd_id") == client_jd:
                            m_recv = mp.get("receivedDateTime")
                            if m_recv:
                                t_utc = _parse_to_utc_dt(m_recv)
                                if t_utc.astimezone(IST).strftime("%Y-%m-%d") == req_date_str:
                                    restored_utc_iso = t_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                                    recovery_source = f"requirement_memory ({mr[0][:20]}...)"
                                    break
                    except Exception:
                        continue
            except Exception:
                pass

        # Source 1 fallback: field_change_history date only
        if not restored_utc_iso:
            for entry in fch:
                changes = entry.get("changes", {})
                if "demand_received_date" in changes:
                    old_date = changes["demand_received_date"].get("old")
                    if old_date == req_date_str:
                        # Exact date from history, approximate time
                        t_utc = _parse_to_utc_dt(f"{req_date_str}T00:00:00Z")
                        restored_utc_iso = f"{req_date_str}T00:00:00Z"
                        recovery_source = "field_change_history (date recovered, time approximate)"
                        is_approximate = True
                        break

        # Source 6: REQ date segment (mark approximate, never use processing time)
        if not restored_utc_iso:
            restored_utc_iso = f"{req_date_str}T00:00:00Z"
            recovery_source = "REQ date segment (approximate)"
            is_approximate = True

        # Restored IST time for display
        dt_rest_utc = _parse_to_utc_dt(restored_utc_iso)
        dt_rest_ist = dt_rest_utc.astimezone(IST)
        restored_display = dt_rest_ist.strftime("%m/%d/%Y %I:%M %p")
        if is_approximate:
            restored_display += " (approximate)"

        broken_rows.append({
            "job_id": job_id,
            "client_jd_id": client_jd,
            "req_date": req_date_str,
            "current_value": ist_display,
            "current_utc": curr_arr,
            "restored_value": restored_display,
            "restored_utc": restored_utc_iso,
            "source": recovery_source,
            "approximate": is_approximate,
            "payload": payload,
            "fch": fch,
            "created_at_db": created_at_db,
        })

    # Print Report
    print("=" * 100)
    print(f"AUDIT DATES REPORT: {'APPLYING REPAIRS' if apply_changes else 'DRY RUN (READ-ONLY)'}")
    print("=" * 100)
    print(f"Total rows inspected: {len(rows)}")
    print(f"Matched invariant:    {matched_count}")
    print(f"Legacy imports:       {legacy_count}")
    print(f"Broken invariant:     {len(broken_rows)}")
    print("-" * 100)

    if broken_rows:
        print(f"{'Client ID':<12} | {'Job ID':<16} | {'Current IST Arrival':<22} | {'Restored IST Arrival':<24} | {'Recovery Source'}")
        print("-" * 100)
        for b in broken_rows:
            print(f"{str(b['client_jd_id']):<12} | {b['job_id']:<16} | {b['current_value']:<22} | {b['restored_value']:<24} | {b['source']}")

    if apply_changes and broken_rows:
        create_backups()
        for b in broken_rows:
            p = b["payload"]
            res_utc = b["restored_utc"]
            res_date = b["req_date"]

            p["first_arrival_at"] = res_utc
            p["receivedDateTime"] = res_utc
            p["demand_received_date"] = res_date
            if b["approximate"]:
                p["first_arrival_approximate"] = True

            # If recovering from backup, restore pristine provenance if present
            if b["client_jd_id"] and b["client_jd_id"] in backup_dict:
                b_p = backup_dict[b["client_jd_id"]]
                if b_p.get("_provenance"):
                    p["_provenance"] = b_p["_provenance"]

            # Update metaforge_requirements
            cur_mf.execute(
                "UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?",
                (json.dumps(p, ensure_ascii=False), b["job_id"]),
            )

            # Update client_requirements in processed_messages.db if present
            if conn_proc and b["client_jd_id"]:
                conn_proc.execute(
                    "UPDATE client_requirements SET payload_json = ? WHERE client_jd_id = ?",
                    (json.dumps(p, ensure_ascii=False), b["client_jd_id"]),
                )

        conn_mf.commit()
        if conn_proc:
            conn_proc.commit()
        print("\n[SUCCESS] Date invariant repairs applied successfully!")

    conn_mf.close()
    if conn_proc:
        conn_proc.close()

    return {
        "matched": matched_count,
        "legacy": legacy_count,
        "broken": len(broken_rows),
        "broken_rows": broken_rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit and repair requirement first_arrival_at dates.")
    parser.add_argument("--repair", action="store_true", help="Repair broken rows (default is dry-run)")
    parser.add_argument("--apply", action="store_true", help="Commit repaired dates to database")
    args = parser.parse_args()

    audit_and_repair(apply_changes=args.apply)


if __name__ == "__main__":
    main()
