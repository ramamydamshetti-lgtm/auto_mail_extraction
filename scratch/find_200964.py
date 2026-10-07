import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

# Search for 200964-1
for tbl in ["client_requirements", "pending_reviews", "requirement_memory"]:
    cur = conn_proc.execute(f"SELECT * FROM {tbl} WHERE payload_json LIKE '%200964-1%'")
    rows = cur.fetchall()
    print(f"proc_db {tbl} with 200964-1: {len(rows)}")
    for r in rows:
        print(" ", r[0], r[1] if len(r)>1 else "")

cur = conn_mf.execute("SELECT job_id, client_jd_id, created_at, updated_at, payload_json FROM metaforge_requirements WHERE client_jd_id = '200964-1' OR payload_json LIKE '%200964-1%'")
rows = cur.fetchall()
print(f"mf_db metaforge_requirements with 200964-1: {len(rows)}")
for r in rows:
    p = json.loads(r[4])
    print(" ", r[0], r[1], r[2], r[3], p.get("job_title"), p.get("location"), p.get("demand_received_date"))

conn_proc.close()
conn_mf.close()
