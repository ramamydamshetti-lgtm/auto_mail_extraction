"""Re-post recent requirement_memory payloads to MetaForge API (after ingest fix)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
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
    since = datetime.now(timezone.utc) - timedelta(days=2)

    ok = 0
    fail = 0
    with ProcessedStore(settings.processed_db) as store:
        rows = store._conn.execute(
            """SELECT payload_json, source_graph_id, created_at
               FROM requirement_memory
               WHERE created_at >= ?
               ORDER BY created_at ASC""",
            (since.isoformat(),),
        ).fetchall()
        seen: set[str] = set()
        for payload_json, graph_id, _created in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                fail += 1
                continue
            job_id = str(payload.get("job_id") or "").strip()
            dedupe = job_id or str(graph_id or "")
            if not dedupe or dedupe in seen:
                continue
            seen.add(dedupe)
            try:
                send_to_metaforge(payload, settings)
                if graph_id:
                    store.pipeline_mark_synced(str(graph_id), f"resync_memory job_id={job_id}")
                ok += 1
                print(f"OK {job_id or graph_id}")
            except Exception as exc:
                fail += 1
                print(f"FAIL {job_id or graph_id}: {exc}")

    print(f"Done: synced={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
