"""Temporary diagnostic — inspect pipeline state."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
from config import Settings

load_dotenv()
db = Path(Settings.from_env().processed_db)
if not db.is_absolute():
    db = ROOT / db
c = sqlite3.connect(db)
print("DB:", db)
print("=== State counts ===")
for row in c.execute("SELECT state, COUNT(*) FROM pipeline_state GROUP BY state ORDER BY 2 DESC"):
    print(row)
print("\n=== Stuck queued/processing ===")
for row in c.execute(
    "SELECT graph_id, state, updated_at, substr(detail,1,80) FROM pipeline_state "
    "WHERE state IN ('queued','processing') ORDER BY updated_at DESC LIMIT 20"
):
    print(row)
print("\n=== requirement_memory ===")
print("rows", c.execute("SELECT COUNT(*) FROM requirement_memory").fetchone())
print(
    "join pending_sync",
    c.execute(
        """SELECT COUNT(*) FROM pipeline_state ps
           JOIN requirement_memory rm ON rm.source_graph_id = ps.graph_id
           WHERE ps.state = 'pending_sync'"""
    ).fetchone(),
)

print("\n=== Recent updates (last 15) ===")
for row in c.execute(
    "SELECT state, updated_at, substr(detail,1,80) FROM pipeline_state "
    "ORDER BY updated_at DESC LIMIT 15"
):
    print(row)
