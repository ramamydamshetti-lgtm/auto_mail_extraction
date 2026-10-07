import sqlite3
import json
import os
from pathlib import Path

from requirement_identity import compute_requirement_identity, clean_client_jd_id
from requirement_comparator import build_requirement_profile

db_path = Path("data/metaforge_requirements.db")
pm_path = Path("data/processed_messages.db")

conn_mf = sqlite3.connect(db_path)
conn_mf.row_factory = sqlite3.Row

# Known true duplicates to merge into canonical records:
# (duplicate_job_id, canonical_job_id)
DUPLICATE_MERGE_PAIRS = [
    ("ACC-2026-09-29-001", "2026/09/29-025"),
    ("2026/10/05-012", "2026/09/20-004"),
    ("2026/10/06-005", "2026/09/23-021"),
    ("2026/10/06-003", "2026/09/23-019"),
    ("2026/09/20-012", "2026/09/07-021"),
    ("2026/09/20-011", "2026/09/04-002"),
    ("2026/09/29-001", "2026/09/08-006"),
    ("2026/09/21-001", "2026/09/11-051"),
    ("2026/10/07-009", "2026/09/11-040"),
    ("2026/09/11-002", "2026/09/11-001"),
]

print("Starting duplicate merge and synchronization...")

for dup_id, can_id in DUPLICATE_MERGE_PAIRS:
    dup_row = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (dup_id,)).fetchone()
    can_row = conn_mf.execute("SELECT * FROM metaforge_requirements WHERE job_id = ?", (can_id,)).fetchone()
    if dup_row and can_row:
        p_dup = json.loads(dup_row["payload_json"])
        p_can = json.loads(can_row["payload_json"])

        # Merge fields from duplicate into canonical if missing
        fields_to_merge = ["skills", "mandatory_skills", "location", "overall_experience", "number_of_positions", "monthly_budget", "yearly_budget", "client_jd_id", "notice_period"]
        for f in fields_to_merge:
            if not p_can.get(f) and p_dup.get(f):
                p_can[f] = p_dup[f]

        # Preserve former_job_id
        formers = set()
        if can_row["former_job_id"]:
            formers.add(can_row["former_job_id"])
        if p_can.get("former_job_id"):
            formers.add(p_can["former_job_id"])
        formers.add(dup_id)
        if dup_row["former_job_id"]:
            formers.add(dup_row["former_job_id"])
        former_str = ",".join(sorted(list(formers)))
        p_can["former_job_id"] = former_str

        # Merge field change history
        hist_can = json.loads(can_row["field_change_history"] or "[]")
        hist_dup = json.loads(dup_row["field_change_history"] or "[]")
        combined_hist = hist_can + hist_dup
        combined_hist.append({
            "changed_at": p_dup.get("first_arrival_at") or dup_row["created_at"],
            "source_email_id": p_dup.get("graphMessageId") or "",
            "changes": {"merged_duplicate_record": {"old": dup_id, "canonical": can_id}},
        })

        # Update canonical record
        conn_mf.execute(
            """UPDATE metaforge_requirements
               SET payload_json = ?, field_change_history = ?, former_job_id = ?
               WHERE job_id = ?""",
            (json.dumps(p_can, ensure_ascii=False), json.dumps(combined_hist, ensure_ascii=False), former_str, can_id)
        )

        # Delete duplicate row
        conn_mf.execute("DELETE FROM metaforge_requirements WHERE job_id = ?", (dup_id,))
        print(f"Merged duplicate {dup_id} into canonical {can_id}")

conn_mf.commit()

# Pass 2: Backfill identity and client_jd_id columns across all remaining records
rows = conn_mf.execute("SELECT job_id, client_jd_id, identity, payload_json FROM metaforge_requirements").fetchall()
print(f"\nBackfilling identity and client_jd_id for {len(rows)} records...")

updated_count = 0
for r in rows:
    p = json.loads(r["payload_json"])
    cjd = clean_client_jd_id(r["client_jd_id"] or p.get("client_jd_id"))
    ident = r["identity"] or p.get("identity")

    if not ident:
        ident = compute_requirement_identity(
            client=p.get("requirement_from") or p.get("client_key") or p.get("client"),
            client_jd_id=cjd,
            job_title=p.get("job_title"),
            location=p.get("location"),
            experience=p.get("overall_experience") or p.get("experience_level"),
            mandatory_skills=p.get("mandatory_skills"),
        )
        p["identity"] = ident

    if cjd and not p.get("client_jd_id"):
        p["client_jd_id"] = cjd

    conn_mf.execute(
        """UPDATE metaforge_requirements
           SET identity = ?, client_jd_id = ?, payload_json = ?
           WHERE job_id = ?""",
        (ident, cjd, json.dumps(p, ensure_ascii=False), r["job_id"])
    )
    updated_count += 1

conn_mf.commit()
print(f"Backfilled {updated_count} records in metaforge_requirements.")

# Pass 3: Synchronize requirement_identity in processed_messages.db
if pm_path.exists():
    conn_pm = sqlite3.connect(pm_path)
    print("\nSynchronizing requirement_identity in processed_messages.db...")
    all_rows = conn_mf.execute("SELECT job_id, client_jd_id, identity, payload_json, created_at FROM metaforge_requirements").fetchall()
    
    for r in all_rows:
        p = json.loads(r["payload_json"])
        c = p.get("requirement_from") or p.get("client_key") or "unknown"
        from requirement_identity import normalize_client_key
        c_norm = normalize_client_key(c)
        cjd = r["client_jd_id"]
        ident = r["identity"]
        prof = p.get("_profile") or build_requirement_profile(p)
        city = prof.get("city")
        gid = p.get("graphMessageId") or (p.get("_provenance") or {}).get("graph_message_id")
        created_at = r["created_at"] or ""

        conn_pm.execute(
            """INSERT INTO requirement_identity
               (identity, client, client_jd_id, city, state, first_seen, last_seen, times_seen,
                original_record_ref, last_graph_id, profile_json, text_fingerprint)
               VALUES (?, ?, ?, ?, 'stored', ?, ?, 1, ?, ?, ?, ?)
               ON CONFLICT(identity) DO UPDATE SET
                   original_record_ref = excluded.original_record_ref,
                   profile_json = excluded.profile_json,
                   state = 'stored',
                   client_jd_id = COALESCE(excluded.client_jd_id, requirement_identity.client_jd_id),
                   city = COALESCE(excluded.city, requirement_identity.city)""",
            (
                ident,
                c_norm,
                cjd,
                city,
                created_at,
                created_at,
                r["job_id"],
                gid,
                json.dumps(prof, ensure_ascii=False),
                prof.get("text_fingerprint") or "",
            )
        )
    conn_pm.commit()
    conn_pm.close()
    print("requirement_identity synchronization complete.")

conn_mf.close()
print("Done!")
