"""
Post requirement_memory payloads to the API in received-date order.
Strips local job_id so the backend allocates REQ-YYYY-MM-DD-001, 002, … on the target DB.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from config import Settings
from metaforge_api import send_to_metaforge
from processed_store import ProcessedStore
from utils import setup_logging


def _received_day(payload: dict) -> str:
    for key in (
        "receivedDateTime",
        "email_received_iso",
        "demand_received_date",
        "received_at",
    ):
        raw = str(payload.get(key) or "").strip()
        if len(raw) >= 10:
            return raw[:10]
    return ""


def _received_sort_key(payload: dict) -> str:
    for key in ("receivedDateTime", "email_received_iso", "received_at"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            return raw
    day = _received_day(payload)
    return f"{day}T00:00:00Z" if day else ""


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ordered sync from requirement_memory to API")
    parser.add_argument("--days", type=int, default=2, help="Calendar days ending today (default 2)")
    parser.add_argument("--since", default=None, help="ISO date YYYY-MM-DD (overrides --days)")
    args = parser.parse_args()

    load_dotenv()
    os.chdir(ROOT)
    settings = Settings.from_env()
    setup_logging(settings.log_level)

    if args.since:
        start_day = date.fromisoformat(args.since)
    else:
        today = date.today()
        start_day = today - timedelta(days=max(1, args.days) - 1)

    ok = 0
    fail = 0
    skipped = 0

    with ProcessedStore(settings.processed_db) as store:
        rows = store._conn.execute(
            "SELECT payload_json, source_graph_id FROM requirement_memory ORDER BY created_at ASC"
        ).fetchall()

        candidates: list[tuple[str, dict, str]] = []
        for payload_json, graph_id in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                fail += 1
                continue
            day = _received_day(payload)
            if not day:
                continue
            try:
                if date.fromisoformat(day) < start_day:
                    continue
            except ValueError:
                continue
            candidates.append((_received_sort_key(payload), payload, str(graph_id or "")))

        candidates.sort(key=lambda x: x[0])

        seen_graph: set[str] = set()
        for _sort_key, payload, graph_id in candidates:
            if graph_id and graph_id in seen_graph:
                skipped += 1
                continue
            if graph_id:
                seen_graph.add(graph_id)

            out = dict(payload)
            out.pop("job_id", None)
            out.pop("client_jd_id", None)
            out["pipeline_extracted"] = True
            if graph_id:
                out.setdefault("graphMessageId", graph_id)
                out.setdefault("graph_message_id", graph_id)

            try:
                send_to_metaforge(out, settings)
                if graph_id:
                    store.pipeline_mark_synced(graph_id, "sync_memory_ordered")
                ok += 1
                title = str(out.get("job_title") or out.get("jobTitle") or "")[:60]
                recv_day = _received_day(out)
                print(f"OK {recv_day} {title}")
            except Exception as exc:
                fail += 1
                recv_day = _received_day(out)
                print(f"FAIL {recv_day}: {exc}")

    print(f"Done: synced={ok} failed={fail} skipped_dup={skipped} since={start_day.isoformat()}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
