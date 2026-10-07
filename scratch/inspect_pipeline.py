import os
import glob
import sqlite3
import json

dbs = glob.glob("*.db") + glob.glob("*/*.db")
for db in dbs:
    print("DB:", db)
    try:
        conn = sqlite3.connect(db)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tbl_names = [t[0] for t in tables]
        print("  Tables:", tbl_names)
        for tbl in ['metaforge_requirements', 'client_requirements', 'pending_reviews', 'email_dispositions', 'requirement_memory']:
            if tbl in tbl_names:
                count = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                print(f"    {tbl}: {count} rows")
        conn.close()
    except Exception as e:
        print("  Error:", e)
