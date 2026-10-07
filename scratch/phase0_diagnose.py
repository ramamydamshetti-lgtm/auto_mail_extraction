import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

print("=== PROCESSED_MESSAGES.DB ===")
tables_proc = [r[0] for r in conn_proc.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables_proc:
    cols = [r[1] for r in conn_proc.execute(f"PRAGMA table_info({t})").fetchall()]
    count = conn_proc.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Table {t} ({count} rows): {cols}")

print("\n=== METAFORGE_REQUIREMENTS.DB ===")
tables_mf = [r[0] for r in conn_mf.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables_mf:
    cols = [r[1] for r in conn_mf.execute(f"PRAGMA table_info({t})").fetchall()]
    count = conn_mf.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Table {t} ({count} rows): {cols}")

# Check client_requirements in proc_db
print("\n=== CLIENT_REQUIREMENTS in proc_db ===")
rows = conn_proc.execute("SELECT client_jd_id, requirement_from, status, created_at, updated_at FROM client_requirements ORDER BY updated_at DESC LIMIT 10").fetchall()
for r in rows:
    print(r)

# Check requirements in mf_db
print("\n=== METAFORGE_REQUIREMENTS in mf_db ===")
rows = conn_mf.execute("SELECT job_id, client_jd_id, created_at, updated_at, payload_json FROM metaforge_requirements ORDER BY updated_at DESC LIMIT 10").fetchall()
for r in rows:
    p = json.loads(r[4])
    print(r[0], r[1], r[2], r[3], p.get("job_title"), p.get("location"), p.get("demand_received_date"), p.get("email_received_iso"))

conn_proc.close()
conn_mf.close()
