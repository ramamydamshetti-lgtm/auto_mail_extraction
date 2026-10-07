import sqlite3
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA="

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

print("Checking gid:", gid)
for tbl in ["processed", "pipeline_state", "pending_reviews", "filtered_log", "requirement_memory", "status_history"]:
    cols = [r[1] for r in conn_proc.execute(f"PRAGMA table_info({tbl})").fetchall()]
    matching_cols = [c for c in cols if 'id' in c.lower() or 'source' in c.lower()]
    for c in matching_cols:
        try:
            rows = conn_proc.execute(f"SELECT * FROM {tbl} WHERE {c} = ?", (gid,)).fetchall()
            if rows:
                print(f"Found in proc_db.{tbl}.{c}: {len(rows)} rows")
                for r in rows[:3]:
                    print("  ", r)
        except Exception as e:
            pass

# Check requirement_memory
rows = conn_proc.execute("SELECT id, requirement_from, job_title_norm, created_at FROM requirement_memory WHERE source_graph_id = ?", (gid,)).fetchall()
print(f"requirement_memory rows for gid: {len(rows)}")

conn_proc.close()
conn_mf.close()
