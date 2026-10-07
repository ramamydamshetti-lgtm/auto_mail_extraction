import sqlite3
import json

conn_mf = sqlite3.connect("data/metaforge_requirements.db")
mf_rows = conn_mf.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()
print("metaforge_requirements rows count:", len(mf_rows))
conn_mf.close()

conn_proc = sqlite3.connect("data/processed_messages.db")
cursor = conn_proc.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("processed_messages tables:", tables)
for t in tables:
    count = conn_proc.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {count} rows")

# Check requirement_memory columns
if "requirement_memory" in tables:
    cur = conn_proc.execute("PRAGMA table_info(requirement_memory)")
    print("requirement_memory columns:", [r[1] for r in cur.fetchall()])
    sample = conn_proc.execute("SELECT * FROM requirement_memory LIMIT 2").fetchall()
    print("requirement_memory sample count:", len(sample))

conn_proc.close()
