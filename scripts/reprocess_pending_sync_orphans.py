"""Reprocess pending_sync rows that have no requirement_memory payload."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from outlook_graph import acquire_token_from_env, fetch_message_by_id
from processed_store import ProcessedStore
from utils import setup_logging


def _clear_pipeline_state(store: ProcessedStore, graph_id: str) -> None:
    store._conn.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM processed WHERE graph_id = ?", (graph_id,))
    store._conn.commit()


def main() -> int:
    load_dotenv()
    os.chdir(ROOT)
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    mailbox = settings.mailbox_upn
    token = acquire_token_from_env()
    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)

    synced = 0
    failed = 0
    with ProcessedStore(settings.processed_db) as store:
        rows = store._conn.execute(
            """SELECT ps.graph_id FROM pipeline_state ps
               WHERE ps.state = 'pending_sync'
               AND NOT EXISTS (
                 SELECT 1 FROM requirement_memory rm WHERE rm.source_graph_id = ps.graph_id
               )"""
        ).fetchall()
        for (graph_id,) in rows:
            gid = str(graph_id or "").strip()
            if not gid:
                continue
            try:
                raw = fetch_message_by_id(token, mailbox, gid)
                _clear_pipeline_state(store, gid)
                rows_synced = process_single_message(
                    raw,
                    token=token,
                    mailbox=mailbox,
                    settings=settings,
                    allocator=allocator,
                    store=store,
                    skip_classifier=False,
                    sync_via_task=False,
                )
                if rows_synced > 0:
                    synced += 1
                print(f"OK {gid[:40]}... rows={rows_synced}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {gid[:40]}... {exc}")

    allocator.close()
    print(f"Done orphans: synced_messages={synced} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
