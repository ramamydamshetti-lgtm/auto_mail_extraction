"""
Backfill requirement extraction for a calendar date range (yesterday + today by default).
Clears non-terminal pipeline state and reprocesses with direct API sync (no Celery).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from outlook_graph import GRAPH, _encode_user, acquire_token_from_env
from processed_store import ProcessedStore
from utils import setup_logging


def _clear_pipeline_state(store: ProcessedStore, graph_id: str) -> None:
    store._conn.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM processed WHERE graph_id = ?", (graph_id,))
    store._conn.commit()


def iter_messages_between(
    token: str,
    mailbox: str,
    *,
    start_iso: str,
    end_iso: str,
    top_per_page: int = 50,
):
    select = (
        "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,"
        "isRead,internetMessageId"
    )
    filt = f"receivedDateTime ge {start_iso} and receivedDateTime lt {end_iso}"
    url = (
        f"{GRAPH}/users/{_encode_user(mailbox)}/mailFolders/inbox/messages"
        f"?$orderby=receivedDateTime asc&$select={select}&$top={top_per_page}"
        f"&$filter={quote(filt, safe='')}"
    )
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        r = requests.get(url, headers=headers, timeout=120)
        r.raise_for_status()
        payload = r.json()
        for m in payload.get("value", []):
            yield m
        url = payload.get("@odata.nextLink")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill email extraction for date range")
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Number of calendar days ending today to include (default: 2 = yesterday + today)",
    )
    parser.add_argument("--mailbox", default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even if pipeline_state is synced (use after API ingest fix)",
    )
    args = parser.parse_args()

    load_dotenv()
    os.chdir(ROOT)
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    mailbox = args.mailbox or settings.mailbox_upn

    today = date.today()
    start_day = today - timedelta(days=max(1, args.days) - 1)
    start_iso = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    end_iso = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()

    token = acquire_token_from_env()
    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)

    examined = 0
    reprocessed = 0
    synced_rows = 0
    skipped_terminal = 0

    with ProcessedStore(settings.processed_db) as store:
        for raw in iter_messages_between(
            token, mailbox, start_iso=start_iso, end_iso=end_iso
        ):
            examined += 1
            gid = str(raw.get("id") or "").strip()
            if not gid:
                continue
            state = store.pipeline_get_state(gid)
            if state == "synced" and not args.force:
                skipped_terminal += 1
                continue
            if state or args.force:
                _clear_pipeline_state(store, gid)
            rows = process_single_message(
                raw,
                token=token,
                mailbox=mailbox,
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=False,
                sync_via_task=False,
            )
            if rows > 0:
                reprocessed += 1
                synced_rows += rows

    allocator.close()
    print(
        f"Backfill complete mailbox={mailbox} window={start_day.isoformat()}..{today.isoformat()} "
        f"examined={examined} reprocessed={reprocessed} synced_rows={synced_rows} already_synced={skipped_terminal}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
