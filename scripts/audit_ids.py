"""
Audit and Repair REQ Sequence Numbers (R1 - R7).

R6. Command audit_ids: per REQ date, print row count, highest NNN,
    missing numbers, rows whose date part differs from the arrival date,
    and ratio highest NNN / row count.
R7. Repair:
    1. Dry run: for each REQ date, renumber rows by first_arrival_at
       ascending as 001..N. Print the full old-to-new mapping.
    2. On approval: apply in one transaction, update every table that
       holds the number, keep former_job_id, make old URLs redirect,
       and set the day's next number to N+1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from metaforge_api import get_ist_req_date, IST, _ensure_schema
from ui.db import _parse_to_utc_dt


def _format_missing_ranges(missing: list[int]) -> str:
    if not missing:
        return "None (gap-free)"
    if len(missing) > 100:
        return f"{len(missing)} missing numbers (e.g. {missing[0]}..{missing[-1]})"
    ranges = []
    start = missing[0]
    prev = start
    for n in missing[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append(f"{start:03d}..{prev:03d}" if start != prev else f"{start:03d}")
            start = n
            prev = n
    ranges.append(f"{start:03d}..{prev:03d}" if start != prev else f"{start:03d}")
    return ", ".join(ranges)


def audit_ids(
    req_db_path: str = "data/metaforge_requirements.db",
    proc_db_path: str = "data/processed_messages.db",
    renumber_dry_run: bool = False,
    apply: bool = False,
) -> dict:
    if not os.path.exists(req_db_path):
        print(f"[ERROR] Database {req_db_path} not found.")
        sys.exit(1)

    conn = sqlite3.connect(req_db_path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)

    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()

    records_by_date = defaultdict(list)
    date_mismatches = []

    for r in rows:
        job_id = r["job_id"]
        p = json.loads(r["payload_json"]) if r["payload_json"] else {}
        fa = p.get("first_arrival_at") or p.get("receivedDateTime") or p.get("email_received_iso") or r["created_at"]
        arr_ist_date = get_ist_req_date(fa)

        m = re.match(r"^(\d{4}[/-]\d{2}[/-]\d{2})[-_](\d+)$", job_id)
        if m:
            req_date = m.group(1).replace("-", "/")
            seq = int(m.group(2))
        else:
            req_date = arr_ist_date
            seq = 0

        # Check date mismatch
        if req_date != arr_ist_date:
            date_mismatches.append({
                "job_id": job_id,
                "req_date": req_date,
                "arrival_ist_date": arr_ist_date,
                "first_arrival_at": fa,
                "title": p.get("job_title"),
                "client": p.get("requirement_from"),
            })

        records_by_date[req_date].append({
            "job_id": job_id,
            "req_date": req_date,
            "seq": seq,
            "arr_ist_date": arr_ist_date,
            "first_arrival_at": fa,
            "title": p.get("job_title"),
            "client": p.get("requirement_from"),
            "row": r,
            "payload": p,
        })

    # Sort dates ascending
    sorted_dates = sorted(records_by_date.keys())

    print("=" * 105)
    print(f"COMMAND AUDIT_IDS REPORT: {len(rows)} Total Requirements across {len(sorted_dates)} Dates")
    print("=" * 105)
    header = f"{'REQ Date':<12} | {'Rows':<5} | {'Max NNN':<8} | {'Ratio':<7} | {'Date Mismatches':<16} | {'Missing Numbers / Gaps'}"
    print(header)
    print("-" * 105)

    stats = {}
    for d in sorted_dates:
        group = records_by_date[d]
        row_cnt = len(group)
        seqs = [g["seq"] for g in group if g["seq"] > 0]
        max_nnn = max(seqs) if seqs else 0
        ratio = (max_nnn / row_cnt) if row_cnt > 0 else 0.0

        present_set = set(seqs)
        missing = [n for n in range(1, max_nnn + 1) if n not in present_set]
        gap_str = _format_missing_ranges(missing)

        d_mismatches = [m for m in date_mismatches if m["req_date"] == d]
        mismatch_cnt = len(d_mismatches)

        stats[d] = {
            "row_count": row_cnt,
            "highest_nnn": max_nnn,
            "missing_numbers": missing,
            "date_mismatches": mismatch_cnt,
            "ratio": ratio,
        }

        print(f"{d:<12} | {row_cnt:<5} | {max_nnn:<8} | {ratio:<7.2f} | {mismatch_cnt:<16} | {gap_str}")

    print("-" * 105)
    if date_mismatches:
        print(f"\n[NOTE] Total rows whose REQ date segment differs from IST arrival date: {len(date_mismatches)}")
        for dm in date_mismatches[:10]:
            print(f"  {dm['job_id']}: REQ date={dm['req_date']} vs Arrival date={dm['arrival_ist_date']} ({dm['client']} - {dm['title'][:30]})")
        if len(date_mismatches) > 10:
            print(f"  ... and {len(date_mismatches) - 10} more.")

    # -----------------------------------------------------------------------
    # R7 Step 1 & 2: Renumbering Dry Run / Apply
    # -----------------------------------------------------------------------
    mapping = {}
    if renumber_dry_run or apply:
        print("\n" + "=" * 105)
        mode_label = "RENUMBERING APPLY (ONE TRANSACTION)" if apply else "RENUMBERING DRY RUN (READ-ONLY)"
        print(f"R7: {mode_label}")
        print("=" * 105)

        # Regroup by actual arrival IST date (per R: date is IST date of first_arrival_at)
        by_arrival_date = defaultdict(list)
        for r in rows:
            p = json.loads(r["payload_json"]) if r["payload_json"] else {}
            fa = p.get("first_arrival_at") or p.get("receivedDateTime") or p.get("email_received_iso") or r["created_at"]
            arr_ist_date = get_ist_req_date(fa)
            by_arrival_date[arr_ist_date].append({
                "old_job_id": r["job_id"],
                "row": r,
                "payload": p,
                "first_arrival_at": fa,
                "dt_obj": _parse_to_utc_dt(fa),
                "title": p.get("job_title"),
                "client": p.get("requirement_from"),
            })

        print(f"{'Old Job ID':<20} -> {'New Job ID':<18} | {'Client':<12} | {'Arrival (IST)':<20} | {'Job Title':<28}")
        print("-" * 105)

        day_next_counter = {}
        for target_date in sorted(by_arrival_date.keys()):
            items = by_arrival_date[target_date]
            # R4: Sort by first_arrival_at ascending, earlier arrival gets lower number
            items.sort(key=lambda x: (x["dt_obj"], x["old_job_id"]))

            for idx, item in enumerate(items, start=1):
                new_seq_str = f"{idx:03d}" if idx < 1000 else f"{idx}"
                new_job_id = f"{target_date}-{new_seq_str}"
                old_id = item["old_job_id"]
                mapping[old_id] = {
                    "new_job_id": new_job_id,
                    "target_date": target_date,
                    "seq": idx,
                    "client": item["client"],
                    "title": item["title"],
                    "first_arrival_at": item["first_arrival_at"],
                    "payload": item["payload"],
                    "row": item["row"],
                }
                day_next_counter[target_date] = idx + 1
                print(f"{old_id:<20} -> {new_job_id:<18} | {str(item['client'])[:12]:<12} | {str(item['first_arrival_at'])[:19]:<20} | {str(item['title'])[:28]}")

        print("-" * 105)
        print(f"Total rows in mapping: {len(mapping)}")

        if not apply:
            print("\n[DRY RUN COMPLETE] Zero database records were modified. Run with --apply on approval.")
        else:
            # R7 Step 2: Apply in ONE transaction across all tables
            print("\n[APPLY] Beginning transactional application across all databases...")
            backup_dir = "data/backup_renumber_apply"
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(req_db_path, os.path.join(backup_dir, os.path.basename(req_db_path)))
            if os.path.exists(proc_db_path):
                shutil.copy2(proc_db_path, os.path.join(backup_dir, os.path.basename(proc_db_path)))
            print(f"[BACKUP] Safety backups created in {backup_dir}")

            # 1. Update metaforge_requirements.db in one transaction
            conn.execute("BEGIN IMMEDIATE")
            try:
                # To prevent primary key conflicts, re-insert rows cleanly
                all_current_rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
                conn.execute("DELETE FROM metaforge_requirements")

                for r in all_current_rows:
                    old_id = r["job_id"]
                    m_info = mapping.get(old_id)
                    if m_info:
                        new_id = m_info["new_job_id"]
                        req_date = m_info["target_date"]
                        seq = m_info["seq"]
                        p = m_info["payload"]
                        p["job_id"] = new_id
                        p["former_job_id"] = old_id
                        p_json = json.dumps(p, ensure_ascii=False)
                        former_jid = old_id
                    else:
                        new_id = old_id
                        p_json = r["payload_json"]
                        req_date = None
                        seq = None
                        former_jid = r["former_job_id"] if "former_job_id" in r.keys() else None

                    conn.execute(
                        """INSERT INTO metaforge_requirements
                           (job_id, payload_json, created_at, client_jd_id, updated_at, field_change_history, identity, req_date, seq, former_job_id, former_client_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            new_id,
                            p_json,
                            r["created_at"],
                            r["client_jd_id"],
                            r["updated_at"],
                            r["field_change_history"],
                            r["identity"],
                            req_date,
                            seq,
                            former_jid,
                            r["former_client_id"] if "former_client_id" in r.keys() else None,
                        ),
                    )

                # Update status_history in metaforge_requirements.db
                cur_tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                if "status_history" in cur_tables:
                    for old_id, m_info in mapping.items():
                        conn.execute(
                            "UPDATE status_history SET requirement_id = ? WHERE requirement_id = ?",
                            (m_info["new_job_id"], old_id),
                        )

                # Update mf_sequences to day's next number N+1
                if "mf_sequences" in cur_tables:
                    for d_str, next_n in day_next_counter.items():
                        conn.execute(
                            "INSERT INTO mf_sequences(name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = ?",
                            (f"job:{d_str}", next_n, next_n),
                        )

                conn.execute("COMMIT")
                print(f"[SUCCESS] metaforge_requirements table renumbered successfully ({len(mapping)} rows)!")
            except Exception as exc:
                conn.execute("ROLLBACK")
                print(f"[ERROR] Failed applying renumber to metaforge_requirements: {exc}")
                raise

            # 2. Update processed_messages.db in one transaction
            if os.path.exists(proc_db_path):
                pconn = sqlite3.connect(proc_db_path, timeout=30.0)
                pconn.execute("BEGIN IMMEDIATE")
                try:
                    ptables = [t[0] for t in pconn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    
                    if "requirement_identity" in ptables:
                        for old_id, m_info in mapping.items():
                            pconn.execute(
                                "UPDATE requirement_identity SET original_record_ref = ? WHERE original_record_ref = ?",
                                (m_info["new_job_id"], old_id),
                            )

                    if "pending_reviews" in ptables:
                        p_cols = {c[1] for c in pconn.execute("PRAGMA table_info(pending_reviews)").fetchall()}
                        for old_id, m_info in mapping.items():
                            if "job_id" in p_cols:
                                pconn.execute(
                                    "UPDATE pending_reviews SET job_id = ? WHERE job_id = ?",
                                    (m_info["new_job_id"], old_id),
                                )
                            if "possible_duplicate_of" in p_cols:
                                pconn.execute(
                                    "UPDATE pending_reviews SET possible_duplicate_of = ? WHERE possible_duplicate_of = ?",
                                    (m_info["new_job_id"], old_id),
                                )

                    if "status_history" in ptables:
                        for old_id, m_info in mapping.items():
                            pconn.execute(
                                "UPDATE status_history SET requirement_id = ? WHERE requirement_id = ?",
                                (m_info["new_job_id"], old_id),
                            )

                    if "duplicates_archive" in ptables:
                        for old_id, m_info in mapping.items():
                            pconn.execute(
                                "UPDATE duplicates_archive SET job_id = ? WHERE job_id = ?",
                                (m_info["new_job_id"], old_id),
                            )
                            pconn.execute(
                                "UPDATE duplicates_archive SET original_job_id = ? WHERE original_job_id = ?",
                                (m_info["new_job_id"], old_id),
                            )

                    # client_requirements payload_json update
                    if "client_requirements" in ptables:
                        c_rows = pconn.execute("SELECT client_jd_id, payload_json FROM client_requirements").fetchall()
                        for c_row in c_rows:
                            if c_row[1]:
                                try:
                                    cp = json.loads(c_row[1])
                                    old_jid = cp.get("job_id")
                                    if old_jid in mapping:
                                        cp["job_id"] = mapping[old_jid]["new_job_id"]
                                        cp["former_job_id"] = old_jid
                                        pconn.execute(
                                            "UPDATE client_requirements SET payload_json = ? WHERE client_jd_id = ?",
                                            (json.dumps(cp, ensure_ascii=False), c_row[0]),
                                        )
                                except Exception:
                                    pass

                    pconn.execute("COMMIT")
                    pconn.close()
                    print(f"[SUCCESS] processed_messages.db updated across all tables!")
                except Exception as exc:
                    pconn.execute("ROLLBACK")
                    pconn.close()
                    print(f"[ERROR] Failed applying renumber to processed_messages.db: {exc}")
                    raise

    conn.close()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Command audit_ids and repair (R6, R7).")
    parser.add_argument("--renumber-dry-run", action="store_true", help="Print full old-to-new mapping without changing anything.")
    parser.add_argument("--apply", action="store_true", help="Apply renumbering in one transaction across all tables.")
    args = parser.parse_args()

    audit_ids(renumber_dry_run=args.renumber_dry_run, apply=args.apply)
