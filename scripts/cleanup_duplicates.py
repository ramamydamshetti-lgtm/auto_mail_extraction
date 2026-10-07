"""
Cleanup script for duplicate requirements and old mailbox backlog.
Dry-run by default; pass --apply to execute.

Actions:
1. Back up databases first when --apply is set.
2. Find duplicates in metaforge_requirements, pending_reviews, and client_requirements using universal requirement identity.
   Keep the earliest record; move duplicates to duplicates_archive.
3. Find rows whose received date is before INGEST_START_DATETIME and move them to archived_backlog.
4. Seed requirement_identity from the rows that remain, recording times_seen and last_seen.
5. Print detailed counts and lists of known pairs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from requirement_identity import clean_client_jd_id, compute_requirement_identity
from requirement_comparator import build_requirement_profile, compare_requirements, normalize_city


def _parse_to_utc_dt(dt_val: Any) -> datetime:
    """Parse any datetime value into a timezone-aware UTC datetime object."""
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


def run_cleanup(
    *,
    data_dir: Path | str,
    cutoff_iso: str | None = None,
    apply: bool = False,
    metaforge_db_path: Path | str | None = None,
    processed_db_path: Path | str | None = None,
) -> dict[str, Any]:
    data_dir = Path(data_dir)
    mf_db = Path(metaforge_db_path) if metaforge_db_path else (data_dir / "metaforge_requirements.db")
    pm_db = Path(processed_db_path) if processed_db_path else (data_dir / "processed_messages.db")

    if not mf_db.exists() and not pm_db.exists():
        print(f"No databases found in {data_dir}")
        return {"error": "Databases not found"}

    # Load cutoff datetime
    if not cutoff_iso:
        try:
            rules_path = _ROOT / "config" / "pipeline_rules.json"
            if rules_path.exists():
                with open(rules_path, "r", encoding="utf-8") as f:
                    rdata = json.load(f)
                    cutoff_iso = rdata.get("ingest_start_datetime")
        except Exception:
            pass

    cutoff_dt = _parse_to_utc_dt(cutoff_iso) if cutoff_iso else None

    # Step 1: Backup if apply is True
    if apply:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        for p in [mf_db, pm_db]:
            if p.exists():
                bak_path = p.with_suffix(f".db.bak_{ts}")
                shutil.copy2(p, bak_path)
                print(f"Created backup: {bak_path}")

    # Prepare archive tables
    if apply:
        if mf_db.exists():
            conn_mf = sqlite3.connect(mf_db)
            conn_mf.execute(
                """CREATE TABLE IF NOT EXISTS duplicates_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT,
                    original_id TEXT,
                    identity TEXT,
                    payload_json TEXT,
                    archived_at TEXT,
                    reason TEXT
                )"""
            )
            conn_mf.execute(
                """CREATE TABLE IF NOT EXISTS archived_backlog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT,
                    job_id TEXT,
                    client_jd_id TEXT,
                    identity TEXT,
                    payload_json TEXT,
                    received_date_time TEXT,
                    archived_at TEXT
                )"""
            )
            conn_mf.commit()
            conn_mf.close()

        if pm_db.exists():
            conn_pm = sqlite3.connect(pm_db)
            conn_pm.execute(
                """CREATE TABLE IF NOT EXISTS duplicates_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT,
                    original_id TEXT,
                    identity TEXT,
                    payload_json TEXT,
                    archived_at TEXT,
                    reason TEXT
                )"""
            )
            conn_pm.execute(
                """CREATE TABLE IF NOT EXISTS archived_backlog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT,
                    job_id TEXT,
                    client_jd_id TEXT,
                    identity TEXT,
                    payload_json TEXT,
                    received_date_time TEXT,
                    archived_at TEXT
                )"""
            )
            conn_pm.execute(
                """CREATE TABLE IF NOT EXISTS requirement_identity (
                    identity TEXT PRIMARY KEY,
                    client TEXT NOT NULL,
                    client_jd_id TEXT,
                    state TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    times_seen INTEGER NOT NULL DEFAULT 1,
                    original_record_ref TEXT,
                    last_graph_id TEXT
                )"""
            )
            conn_pm.commit()
            conn_pm.close()

    # Step 2: Collect all records across tables
    records_by_ident: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_scanned = 0

    # 2a. metaforge_requirements
    if mf_db.exists():
        conn = sqlite3.connect(mf_db)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute("SELECT * FROM metaforge_requirements").fetchall():
                total_scanned += 1
                try:
                    p = json.loads(r["payload_json"])
                except Exception:
                    p = {}
                c = p.get("requirement_from") or "unknown"
                cjd = clean_client_jd_id(p.get("client_jd_id") or r["client_jd_id"])
                ident = r["identity"] if ("identity" in r.keys() and r["identity"]) else None
                if not ident:
                    ident = compute_requirement_identity(
                        client=c,
                        client_jd_id=cjd,
                        job_title=p.get("job_title"),
                        location=p.get("location"),
                        experience=p.get("overall_experience") or p.get("experience_level"),
                        mandatory_skills=p.get("mandatory_skills"),
                    )
                prov = p.get("_provenance") or {}
                arr = (
                    prov.get("received_date_time")
                    or p.get("receivedDateTime")
                    or r["created_at"]
                    or ""
                )
                prof = build_requirement_profile(p)
                records_by_ident[ident].append({
                    "db_type": "metaforge",
                    "db_path": mf_db,
                    "table": "metaforge_requirements",
                    "row_id": r["job_id"],
                    "job_id": r["job_id"],
                    "client_jd_id": cjd,
                    "client": c,
                    "title": p.get("job_title") or "",
                    "location": p.get("location") or "",
                    "city": prof.get("city"),
                    "identity": ident,
                    "created_at": r["created_at"] or "",
                    "received_date_time": arr,
                    "payload_json": r["payload_json"],
                    "payload": p,
                    "profile": prof,
                    "state": "stored",
                })
        except Exception as e:
            print(f"Error scanning metaforge_requirements: {e}")
        finally:
            conn.close()

    # 2b. client_requirements & pending_reviews
    if pm_db.exists():
        conn = sqlite3.connect(pm_db)
        conn.row_factory = sqlite3.Row
        for tbl, default_state in [("client_requirements", "stored"), ("pending_reviews", "pending_review")]:
            try:
                for r in conn.execute(f"SELECT * FROM {tbl}").fetchall():
                    total_scanned += 1
                    try:
                        p = json.loads(r["payload_json"])
                    except Exception:
                        p = {}
                    c = p.get("requirement_from") or (r["requirement_from"] if "requirement_from" in r.keys() else "unknown")
                    cjd_raw = p.get("client_jd_id") or (r["client_jd_id"] if "client_jd_id" in r.keys() else None)
                    cjd = clean_client_jd_id(cjd_raw)
                    ident = r["identity"] if ("identity" in r.keys() and r["identity"]) else None
                    if not ident:
                        ident = compute_requirement_identity(
                            client=c,
                            client_jd_id=cjd,
                            job_title=p.get("job_title"),
                            location=p.get("location"),
                            experience=p.get("overall_experience") or p.get("experience_level"),
                            mandatory_skills=p.get("mandatory_skills"),
                        )
                    prov = p.get("_provenance") or {}
                    arr = (
                        prov.get("received_date_time")
                        or p.get("receivedDateTime")
                        or (r["created_at"] if "created_at" in r.keys() else "")
                    )
                    row_id = r["client_jd_id"] if "client_jd_id" in r.keys() and tbl == "client_requirements" else str(r["id"])
                    prof = build_requirement_profile(p)
                    records_by_ident[ident].append({
                        "db_type": "processed",
                        "db_path": pm_db,
                        "table": tbl,
                        "row_id": row_id,
                        "job_id": p.get("job_id") or (r["job_id"] if "job_id" in r.keys() else ""),
                        "client_jd_id": cjd,
                        "client": c,
                        "title": p.get("job_title") or "",
                        "location": p.get("location") or "",
                        "city": prof.get("city"),
                        "identity": ident,
                        "created_at": (r["created_at"] if "created_at" in r.keys() else ""),
                        "received_date_time": arr,
                        "payload_json": r["payload_json"],
                        "payload": p,
                        "profile": prof,
                        "state": default_state,
                    })
            except Exception:
                pass
        conn.close()

    # Step 3: Analyze duplicates and backlog
    duplicates_to_archive: list[dict[str, Any]] = []
    backlog_to_archive: list[dict[str, Any]] = []
    active_kept: list[dict[str, Any]] = []
    known_pairs_found: list[dict[str, Any]] = []

    now_iso = datetime.now(timezone.utc).isoformat()
    rules_cfg = {}
    try:
        rules_path = _ROOT / "config" / "pipeline_rules.json"
        if rules_path.exists():
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_cfg = json.load(f)
    except Exception:
        pass

    for ident, items in records_by_ident.items():
        # Sort items chronologically by arrival time / created_at
        items.sort(key=lambda x: _parse_to_utc_dt(x.get("received_date_time") or x.get("created_at") or ""))

        # Check for known pairs explicitly
        has_ltts_plm_mysore = any(
            "ltts" in str(x.get("client") or "").lower()
            and "plm" in str(x.get("title") or "").lower()
            and "mysore" in str(x.get("location") or "").lower()
            for x in items
        )
        has_accenture_sap_co_mumbai = any(
            "accenture" in str(x.get("client") or "").lower()
            and ("sap co" in str(x.get("title") or "").lower() or "management accounting" in str(x.get("title") or "").lower())
            and ("mumbai" in str(x.get("location") or "").lower() or x.get("client_jd_id") in ("200964-1", "200968-1"))
            for x in items
        )

        if len(items) > 1:
            if has_ltts_plm_mysore:
                known_pairs_found.append({
                    "name": "LTTS PLM Mysore",
                    "identity": ident,
                    "count": len(items),
                    "items": [(x["row_id"], x["table"], x["created_at"]) for x in items],
                })
            if has_accenture_sap_co_mumbai:
                known_pairs_found.append({
                    "name": "Accenture SAP CO Management Accounting Mumbai",
                    "identity": ident,
                    "count": len(items),
                    "items": [(x["row_id"], x["table"], x["created_at"]) for x in items],
                })

        # Earliest record is kept
        kept = items[0]
        # Any other record with same identity is duplicate
        for dup in items[1:]:
            dec, score, rule = compare_requirements(dup.get("profile") or build_requirement_profile(dup["payload"]), kept.get("profile") or build_requirement_profile(kept["payload"]), rules_config=rules_cfg)
            dup["score"] = score
            dup["deciding_rule"] = rule
            dup["matched_id"] = kept["row_id"]
            dup["matched_table"] = kept["table"]
            duplicates_to_archive.append(dup)

        # Check if kept record is before cutoff date
        is_backlog = False
        if cutoff_dt:
            rec_dt = _parse_to_utc_dt(kept.get("received_date_time") or kept.get("created_at") or "")
            if rec_dt != datetime.min.replace(tzinfo=timezone.utc) and rec_dt < cutoff_dt:
                is_backlog = True
                backlog_to_archive.append(kept)

        if not is_backlog:
            active_kept.append({
                "record": kept,
                "times_seen": len(items),
                "first_seen": items[0].get("received_date_time") or items[0].get("created_at") or now_iso,
                "last_seen": items[-1].get("received_date_time") or items[-1].get("created_at") or now_iso,
            })

    # Step 4: Print summary report
    print("\n" + "=" * 60)
    print("           REQUIREMENT CLEANUP SUMMARY REPORT")
    print("=" * 60)
    print(f"Mode: {'APPLY (changes executed)' if apply else 'DRY-RUN (simulation only)'}")
    print(f"Cutoff Date (INGEST_START_DATETIME): {cutoff_iso}")
    print(f"Total records scanned: {total_scanned}")
    print(f"Unique identities found: {len(records_by_ident)}")
    print(f"Duplicates to archive: {len(duplicates_to_archive)}")
    print(f"Backlog records older than cutoff: {len(backlog_to_archive)}")
    print(f"Active unique requirements to keep: {len(active_kept)}")

    print("\n--- Duplicate Decisions Found (Score and Deciding Rule) ---")
    if duplicates_to_archive:
        for d in duplicates_to_archive:
            print(
                f"  * [DUPLICATE] [{d['table']}] ID={d['row_id']} | Client={d['client']} | Title={d['title']} | City={d.get('city')}\n"
                f"      Matched With: [{d.get('matched_table')}] ID={d.get('matched_id')} | Score: {d.get('score', 1.0):.2f} | Deciding Rule: {d.get('deciding_rule', 'IDENTITY_MATCH')}"
            )
    else:
        print("  No duplicates detected.")

    print("\n--- Known Pairs Detected as Duplicates ---")
    if known_pairs_found:
        for kp in known_pairs_found:
            print(f"  * {kp['name']}: identity={kp['identity']}, count={kp['count']}")
            for it in kp["items"]:
                print(f"      - Row {it[0]} in {it[1]} ({it[2]})")
    else:
        # Fallback check across all scanned records
        print("  None detected directly under those strict strings; all duplicate groups listed below:")

    if duplicates_to_archive:
        print("\n--- Sample Duplicates Archive List (first 10) ---")
        for d in duplicates_to_archive[:10]:
            print(f"  - [{d['table']}] ID={d['row_id']} | Client={d['client']} | Title={d['title']} | Identity={d['identity']}")

    # Step 5: Execute changes if apply is True
    if apply:
        print("\nApplying changes to databases...")
        # Archive duplicates
        for d in duplicates_to_archive:
            conn = sqlite3.connect(d["db_path"])
            conn.execute(
                """INSERT INTO duplicates_archive
                   (source_table, original_id, identity, payload_json, archived_at, reason)
                   VALUES (?, ?, ?, ?, ?, 'duplicate_identity')""",
                (d["table"], str(d["row_id"]), d["identity"], d["payload_json"], now_iso),
            )
            # Remove from original table
            if d["table"] == "metaforge_requirements":
                conn.execute("DELETE FROM metaforge_requirements WHERE job_id = ?", (d["row_id"],))
            elif d["table"] == "client_requirements":
                conn.execute("DELETE FROM client_requirements WHERE client_jd_id = ?", (d["row_id"],))
            elif d["table"] == "pending_reviews":
                conn.execute("DELETE FROM pending_reviews WHERE id = ?", (int(d["row_id"]),))
            conn.commit()
            conn.close()

        # Archive backlog
        for b in backlog_to_archive:
            conn = sqlite3.connect(b["db_path"])
            conn.execute(
                """INSERT INTO archived_backlog
                   (source_table, job_id, client_jd_id, identity, payload_json, received_date_time, archived_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (b["table"], b["job_id"], b["client_jd_id"], b["identity"], b["payload_json"], b["received_date_time"], now_iso),
            )
            if b["table"] == "metaforge_requirements":
                conn.execute("DELETE FROM metaforge_requirements WHERE job_id = ?", (b["row_id"],))
            elif b["table"] == "client_requirements":
                conn.execute("DELETE FROM client_requirements WHERE client_jd_id = ?", (b["row_id"],))
            elif b["table"] == "pending_reviews":
                conn.execute("DELETE FROM pending_reviews WHERE id = ?", (int(b["row_id"]),))
            conn.commit()
            conn.close()

        # Seed requirement_identity
        if pm_db.exists():
            conn_pm = sqlite3.connect(pm_db)
            seeded_count = 0
            for ak in active_kept:
                rec = ak["record"]
                prof = rec.get("profile") or build_requirement_profile(rec["payload"])
                conn_pm.execute(
                    """INSERT OR REPLACE INTO requirement_identity
                       (identity, client, client_jd_id, city, state, first_seen, last_seen, times_seen, original_record_ref, profile_json, text_fingerprint)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rec["identity"],
                        rec["client"],
                        rec["client_jd_id"],
                        prof.get("city"),
                        rec["state"],
                        ak["first_seen"],
                        ak["last_seen"],
                        ak["times_seen"],
                        rec["job_id"] or rec["client_jd_id"] or rec["row_id"],
                        json.dumps(prof, ensure_ascii=False),
                        prof.get("text_fingerprint", ""),
                    ),
                )
                seeded_count += 1
            conn_pm.commit()
            conn_pm.close()
            print(f"Successfully seeded {seeded_count} requirement identities into {pm_db.name}")

        print("\n[SUCCESS] Cleanup applied successfully.")
    else:
        print("\n[DRY-RUN] No changes were written to any database. Run with --apply to execute.")

    return {
        "scanned": total_scanned,
        "unique_identities": len(records_by_ident),
        "duplicates": len(duplicates_to_archive),
        "backlog": len(backlog_to_archive),
        "active_kept": len(active_kept),
        "known_pairs": known_pairs_found,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup duplicate requirements and mailbox backlog.")
    parser.add_argument("--data-dir", default=str(_ROOT / "data"), help="Directory containing databases (default: data/)")
    parser.add_argument("--cutoff", default=None, help="INGEST_START_DATETIME cutoff in ISO format")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup changes (default is dry-run)")
    args = parser.parse_args()

    res = run_cleanup(
        data_dir=args.data_dir,
        cutoff_iso=args.cutoff,
        apply=args.apply,
    )
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    raise SystemExit(main())
