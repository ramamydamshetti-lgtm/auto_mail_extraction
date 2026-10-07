import sqlite3, json, hashlib, re

def search_phrase(phrase):
    print(f"\nSearching for '{phrase}':")
    for db_path in ['data/metaforge_requirements.db', 'data/processed_messages.db']:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for tbl in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
            for r in conn.execute(f"SELECT * FROM {tbl}").fetchall():
                blob = json.dumps(list(r))
                if phrase.lower() in blob.lower():
                    print(f"[{db_path} - {tbl}] {blob[:250]}")
        conn.close()

search_phrase("Management Accounting")
