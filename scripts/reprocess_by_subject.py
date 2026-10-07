"""
Find a mailbox message by subject/from hint, clear pipeline skip state, and re-run extraction.
Usage:
  python scripts/reprocess_by_subject.py --subject "WORKDAY | FTE" --from-domain kpmg.com
"""

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
from outlook_graph import acquire_token_from_env, iter_inbox_messages
from processed_store import ProcessedStore
from utils import setup_logging


def _matches(
    raw: dict,
    *,
    subject_hint: str,
    from_domain: str,
    received_prefix: str,
) -> bool:
    subject = str(raw.get("subject") or "")
    from_obj = raw.get("from") or {}
    ea = (from_obj.get("emailAddress") or {}) if isinstance(from_obj, dict) else {}
    from_email = str(ea.get("address") or "").lower()
    received = str(raw.get("receivedDateTime") or "")

    if subject_hint and subject_hint.lower() not in subject.lower():
        return False
    if from_domain and from_domain.lower() not in from_email:
        return False
    if received_prefix and not received.startswith(received_prefix):
        return False
    return True


def _clear_pipeline_state(store: ProcessedStore, graph_id: str) -> None:
    store._conn.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM processed WHERE graph_id = ?", (graph_id,))
    store._conn.execute("DELETE FROM requirement_fingerprints WHERE graph_id = ?", (graph_id,))
    store._conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocess one requirement email from Graph inbox")
    parser.add_argument("--subject", required=True, help="Substring match on subject")
    parser.add_argument("--from-domain", default="", help="Sender email domain, e.g. kpmg.com")
    parser.add_argument("--received-prefix", default="", help="ISO date prefix e.g. 2026-06-08")
    parser.add_argument(
        "--mailbox",
        action="append",
        default=[],
        help="Mailbox UPN (repeatable). Defaults to MAILBOX_UPN and rkarnam@metaforgeit.com",
    )
    parser.add_argument("--limit", type=int, default=300, help="Max inbox messages to scan per mailbox")
    args = parser.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    mailboxes = args.mailbox or [settings.mailbox_upn, "rkarnam@metaforgeit.com"]
    mailboxes = [m for i, m in enumerate(mailboxes) if m and m not in mailboxes[:i]]

    try:
        token = acquire_token_from_env()
    except RuntimeError as exc:
        print(f"Auth failed: {exc}")
        return 1

    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)

    found: tuple[str, dict] | None = None
    for mailbox in mailboxes:
        print(f"Scanning {mailbox} (limit={args.limit}) ...")
        for raw in iter_inbox_messages(token, mailbox, limit=args.limit):
            if _matches(
                raw,
                subject_hint=args.subject,
                from_domain=args.from_domain,
                received_prefix=args.received_prefix,
            ):
                found = (mailbox, raw)
                break
        if found:
            break

    if not found:
        print("No matching message found in scanned mailboxes.")
        allocator.close()
        return 2

    mailbox, raw = found
    gid = str(raw.get("id") or "").strip()
    subject = str(raw.get("subject") or "")
    print(f"Found: {subject!r} id={gid[:48]}... mailbox={mailbox}")

    with ProcessedStore(settings.processed_db) as store:
        prev = store.pipeline_get_state(gid)
        print(f"Previous pipeline state: {prev or '(none)'}")
        _clear_pipeline_state(store, gid)
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
    print(f"Reprocess finished. Requirement rows synced: {synced}")
    return 0 if synced > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
