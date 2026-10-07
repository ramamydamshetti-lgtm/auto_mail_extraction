"""
Migration: Deduplicate metaforge_requirements.db.

The historical data contains multiple rows for the same client_jd_id because
the identity-based upsert was not active when those rows were inserted.
This migration keeps the most recently created row for each client_jd_id.
"""
import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
LOG = logging.getLogger(__name__)

DB_PATH = "data/metaforge_requirements.db"


def run_dedup():
    if not Path(DB_PATH).exists():
        LOG.error("Database not found: %s", DB_PATH)
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find all duplicated client_jd_ids
    dups = conn.execute("""
        SELECT client_jd_id, COUNT(*) as cnt
        FROM metaforge_requirements
        WHERE client_jd_id IS NOT NULL AND client_jd_id != ''
        GROUP BY client_jd_id
        HAVING cnt > 1
        ORDER BY cnt DESC
    """).fetchall()

    LOG.info("Found %d client_jd_ids with duplicate rows", len(dups))

    total_deleted = 0
    for dup in dups:
        cjd = dup['client_jd_id']
        cnt = dup['cnt']

        # Get all rows for this client_jd_id, ordered by created_at DESC
        rows = conn.execute("""
            SELECT job_id, payload_json, created_at, updated_at, field_change_history
            FROM metaforge_requirements
            WHERE client_jd_id = ?
            ORDER BY COALESCE(updated_at, created_at) DESC
        """, (cjd,)).fetchall()

        if not rows:
            continue

        # Keep the best (most recent) row
        best_row = rows[0]
        keep_job_id = best_row['job_id']

        # Merge all field_change_history from all duplicates
        merged_hist = []
        seen_hist_keys = set()
        for row in rows:
            try:
                hist = json.loads(row['field_change_history'] or '[]')
                for ev in hist:
                    key = (ev.get('changed_at', ''), ev.get('source_email_id', ''))
                    if key not in seen_hist_keys:
                        seen_hist_keys.add(key)
                        merged_hist.append(ev)
            except Exception:
                pass
        merged_hist.sort(key=lambda x: x.get('changed_at', ''))

        # Update the kept row with merged history
        conn.execute(
            "UPDATE metaforge_requirements SET field_change_history = ? WHERE job_id = ?",
            (json.dumps(merged_hist, ensure_ascii=False), keep_job_id),
        )

        # Delete all other rows with same client_jd_id
        other_job_ids = [r['job_id'] for r in rows[1:]]
        for jid in other_job_ids:
            conn.execute("DELETE FROM metaforge_requirements WHERE job_id = ?", (jid,))
        total_deleted += len(other_job_ids)

    conn.commit()

    # Verify
    remaining_dups = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT client_jd_id FROM metaforge_requirements
            WHERE client_jd_id IS NOT NULL AND client_jd_id != ''
            GROUP BY client_jd_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    total_remaining = conn.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
    conn.close()

    LOG.info("Deduplication complete: deleted=%d rows, remaining=%d, remaining_dups=%d",
             total_deleted, total_remaining, remaining_dups)

    if remaining_dups == 0:
        LOG.info("PASS: No duplicate client_jd_ids remain in metaforge_requirements.db")
    else:
        LOG.error("FAIL: %d duplicate client_jd_ids still exist!", remaining_dups)


if __name__ == "__main__":
    run_dedup()
