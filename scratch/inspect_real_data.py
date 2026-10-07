import sqlite3
import json
import os

print("=== metaforge_requirements.db ===")
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    cur = conn.cursor()
    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        count = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"Table {t} count: {count}")
        if count > 0:
            rows = cur.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
            for r in rows:
                print("  Sample row:", r)

print("\n=== processed_messages.db ===")
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables in processed_messages.db:", tables)
    for t in tables:
        count = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"Table {t} count: {count}")
        if count > 0:
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]
            print("  Cols:", cols)

print("\n=== latest_500_all.json ===")
if os.path.exists("latest_500_all.json"):
    with open("latest_500_all.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        print("Count in latest_500_all.json:", len(data))
        if len(data) > 0:
            print("Sample 0 keys:", list(data[0].keys()))
