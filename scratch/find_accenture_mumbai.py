import sqlite3
import json

for db_path in ['data/metaforge_requirements.db', 'data/processed_messages.db']:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\nDB: {db_path}, Tables: {tables}")
    for tbl in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            for r in rows:
                blob = json.dumps([str(v) for v in r])
                if 'management accounting' in blob.lower() and 'mumbai' in blob.lower():
                    print(f"  [{tbl}] {blob[:200]}")
        except Exception as e:
            pass
    conn.close()
