"""
Re-sync requirements stuck in pipeline_state=pending_sync using stored requirement_memory payloads.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from config import Settings
from metaforge_api import send_to_metaforge
from processed_store import ProcessedStore
from utils import setup_logging


def main() -> int:
    load_dotenv()
    os.chdir(ROOT)
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    synced = 0
    failed = 0
    skipped = 0

    with ProcessedStore(settings.processed_db) as store:
        rows = store._conn.execute(
            """SELECT ps.graph_id, rm.payload_json
               FROM pipeline_state ps
               JOIN requirement_memory rm ON rm.source_graph_id = ps.graph_id
               WHERE ps.state = 'pending_sync'
               ORDER BY ps.updated_at ASC"""
        ).fetchall()

        seen: set[str] = set()
        for graph_id, payload_json in rows:
            gid = str(graph_id or "").strip()
            if not gid or gid in seen:
                continue
            seen.add(gid)
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                failed += 1
                print(f"FAIL invalid JSON for {gid[:40]}...")
                continue
            try:
                send_to_metaforge(payload, settings)
                store.pipeline_mark_synced(gid, "retry_pending_sync")
                synced += 1
                print(f"OK synced {gid[:40]}... job_id={payload.get('job_id')}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {gid[:40]}... {exc}")

        # pending_sync rows without memory cannot be reconstructed here
        orphan = store._conn.execute(
            """SELECT COUNT(*) FROM pipeline_state ps
               WHERE ps.state = 'pending_sync'
               AND NOT EXISTS (
                 SELECT 1 FROM requirement_memory rm WHERE rm.source_graph_id = ps.graph_id
               )"""
        ).fetchone()[0]
        if orphan:
            skipped = int(orphan)
            print(f"WARN {orphan} pending_sync row(s) have no requirement_memory payload")

    print(f"Done: synced={synced} failed={failed} orphans={skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
