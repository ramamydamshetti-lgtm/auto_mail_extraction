"""Reset pipeline rows stuck in queued/processing so the scheduler can re-enqueue them."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from config import Settings
from processed_store import ProcessedStore


def main() -> int:
    load_dotenv()
    os.chdir(ROOT)
    settings = Settings.from_env()
    with ProcessedStore(settings.processed_db) as store:
        cur = store._conn.execute(
            "DELETE FROM pipeline_state WHERE state IN ('queued', 'processing')"
        )
        store._conn.commit()
        print(f"Removed {cur.rowcount} stuck queued/processing row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
