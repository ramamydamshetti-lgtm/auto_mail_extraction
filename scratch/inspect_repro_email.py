import sqlite3, json

for db_path in ["data/processed_messages.db", "data/metaforge_requirements.db"]:
    print(f"=== DB: {db_path} ===")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        if t in ["metaforge_requirements", "client_requirements", "pending_reviews"]:
            rows = conn.execute(f"SELECT * FROM {t} WHERE payload_json LIKE '%RQ056293%' OR payload_json LIKE '%vaishnavi%'").fetchall()
            print(f" Matches in {t}: {len(rows)}")
            for r in rows:
                print("  Row:", dict(r))
                if 'payload_json' in r.keys():
                    pj = json.loads(r['payload_json'])
                    print("  Payload JSON:")
                    print(json.dumps(pj, indent=2))
    conn.close()
