import glob
import sqlite3
import json

dbs = glob.glob('**/*.db', recursive=True)
print("Found SQLite DBs:", dbs)

search_ids = ["195414-1", "195379-1", "195320-1", "195398-1", "174902-1", "203501-1", "203486-1", "203489-1", "203495-1"]

for db in dbs:
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"\n=== DB: {db} (Tables: {tables}) ===")
        for t in tables:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            print(f"  Table '{t}': {len(rows)} rows")
            for r in rows:
                row_str = str(dict(r))
                for sid in search_ids:
                    if sid in row_str:
                        print(f"    FOUND {sid} in table '{t}': job_id={r['job_id'] if 'job_id' in r.keys() else 'N/A'}")
    except Exception as e:
        print(f"Error checking {db}: {e}")
