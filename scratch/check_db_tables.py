import sqlite3
import json
import os
import glob

def check_sqlite(path):
    print(f"=== Checking SQLite: {path} ===")
    if not os.path.exists(path):
        print("File does not exist")
        return
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for table in tables:
        count = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  Table: {table} ({count} rows)")
        if count > 0:
            sample = cur.execute(f"SELECT * FROM {table} LIMIT 2").fetchall()
            print("  Sample row:", sample[0])

check_sqlite("data/metaforge_requirements.db")
check_sqlite("data/processed_messages.db")

print("\n=== Checking JSON / CSV files ===")
json_files = glob.glob("*.json") + glob.glob("data/*.json")
for jf in json_files:
    size = os.path.getsize(jf)
    print(f"File: {jf} ({size} bytes)")
