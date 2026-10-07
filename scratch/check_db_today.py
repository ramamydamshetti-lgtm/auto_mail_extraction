import glob
import sqlite3
import json

dbs = glob.glob("**/*.db", recursive=True)
print("Found databases:", dbs)

for db in dbs:
    try:
        conn = sqlite3.connect(db)
        tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"\n--- Database: {db} ---")
        for t in tables:
            cnt = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  Table '{t}': {cnt} rows")
            if t == "metaforge_requirements":
                rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
                for jid, ca, pjson in rows:
                    p = json.loads(pjson)
                    print(f"    - {jid} | Created: {ca} | Client: {p.get('requirement_from')} | Status: {p.get('job_status')}")
        conn.close()
    except Exception as e:
        print(f"Error reading {db}: {e}")
