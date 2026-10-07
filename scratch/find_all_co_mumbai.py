import sqlite3, json

for name, db_path in [("metaforge", "data/metaforge_requirements.db"), ("processed", "data/processed_messages.db")]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for tbl in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
        for r in rows:
            blob = json.dumps([str(v) for v in r])
            if 'management accounting' in blob.lower() and 'mumbai' in blob.lower():
                print(f"[{name}.{tbl}] {blob[:300]}")
    conn.close()
