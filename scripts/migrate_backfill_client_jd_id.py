"""
One-time migration: backfill client_jd_id in metaforge_requirements.db
from payload_json. Run once after the field_change_history schema migration.

This fixes the root cause: historical rows in metaforge_requirements.db were
inserted with client_jd_id=NULL even though the payload contained the real
client ID. After this runs, the identity-based upsert (Rule 1/2) will work
correctly for all existing rows.
"""
import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
LOG = logging.getLogger(__name__)


def run_migration(db_path: str = 'data/metaforge_requirements.db') -> None:
    if not Path(db_path).exists():
        LOG.error("Database not found: %s", db_path)
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure columns exist (safe migration)
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(metaforge_requirements)").fetchall()}
    for col, ddl in [
        ("client_jd_id",         "TEXT"),
        ("updated_at",           "TEXT"),
        ("field_change_history", "TEXT"),
    ]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE metaforge_requirements ADD COLUMN {col} {ddl}")
            LOG.info("Added column: %s", col)

    # Index for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mf_req_client_jd_id ON metaforge_requirements(client_jd_id)")
    conn.commit()

    # Backfill client_jd_id from payload_json
    rows = conn.execute("SELECT job_id, payload_json, created_at, updated_at FROM metaforge_requirements").fetchall()
    LOG.info("Total rows to process: %d", len(rows))

    updated = 0
    already_set = 0
    no_id = 0

    for row in rows:
        job_id = row["job_id"]
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            continue

        cjd = payload.get("client_jd_id") or payload.get("client_jd_id_override") or ""
        cjd = str(cjd).strip()

        # Validate: reject internal system-generated placeholders
        import re
        if cjd and re.match(r"^(ACC|LTTS|REQ)\-\d{4}\-", cjd, re.IGNORECASE):
            cjd = ""

        # Check current state
        cur_cjd_row = conn.execute("SELECT client_jd_id FROM metaforge_requirements WHERE job_id = ?", (job_id,)).fetchone()
        cur_cjd = str(cur_cjd_row["client_jd_id"] or "").strip() if cur_cjd_row else ""

        if cur_cjd:
            already_set += 1
            continue

        if not cjd:
            no_id += 1
            continue

        # Ensure updated_at is set (fallback to created_at)
        updated_at = row["updated_at"] or row["created_at"] or ""

        conn.execute(
            "UPDATE metaforge_requirements SET client_jd_id = ?, updated_at = COALESCE(updated_at, ?) WHERE job_id = ?",
            (cjd, updated_at, job_id),
        )
        updated += 1

    # Ensure all rows have updated_at = created_at if still null
    conn.execute(
        "UPDATE metaforge_requirements SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''"
    )
    # Ensure all rows have field_change_history initialized
    conn.execute(
        "UPDATE metaforge_requirements SET field_change_history = '[]' WHERE field_change_history IS NULL"
    )

    conn.commit()
    conn.close()

    LOG.info("Migration complete: updated=%d, already_set=%d, no_client_id=%d", updated, already_set, no_id)


if __name__ == "__main__":
    run_migration()
