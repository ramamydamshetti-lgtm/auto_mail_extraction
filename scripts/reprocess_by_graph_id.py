"""Reprocess one Graph message by graph_id (clears pipeline skip state first)."""

from __future__ import annotations

import argparse
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


def _clear_pipeline_state(store: ProcessedStore, graph_id: str, inet_id: str = "") -> None:
    store._conn.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM processed WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM requirement_fingerprints WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM duplicate_decisions WHERE source_email_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM seen_messages WHERE graph_id = ?", (graph_id,))
    if inet_id:
        store._conn.execute("DELETE FROM seen_messages WHERE internet_message_id = ?", (inet_id,))
    store._conn.execute("DELETE FROM pending_reviews WHERE graph_id = ?", (graph_id,))
    store._conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-id", required=True)
    parser.add_argument("--mailbox", default="")
    args = parser.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    mailbox = args.mailbox or settings.mailbox_upn
    gid = args.graph_id.strip()

    token = acquire_token_from_env()
    raw = fetch_message_by_id(token, mailbox, gid)
    subject = str(raw.get("subject") or "")
    print(f"Fetched: {subject!r} from {mailbox}")

    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)
    with ProcessedStore(settings.processed_db) as store:
        prev = store.pipeline_get_state(gid)
        print(f"Previous pipeline state: {prev or '(none)'}")
        inet_id = str(raw.get("internetMessageId") or "").strip()
        _clear_pipeline_state(store, gid, inet_id)
        synced = process_single_message(
            raw,
            token=token,
            mailbox=mailbox,
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=False,
            sync_via_task=False,
        )
    allocator.close()
    print(f"Synced rows: {synced}")
    return 0 if synced > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
