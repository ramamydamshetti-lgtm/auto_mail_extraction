import sqlite3
import json

print("=== metaforge_requirements.db ===")
try:
    conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", tables)
    for table in tables:
        tname = table[0]
        cols = conn.execute(f"PRAGMA table_info('{tname}')").fetchall()
        count = conn.execute(f"SELECT COUNT(*) FROM '{tname}'").fetchone()[0]
        print(f"Table '{tname}' ({count} rows):", [c[1] for c in cols])
        row = conn.execute(f"SELECT * FROM '{tname}' LIMIT 1").fetchone()
        if row:
            print("Sample row keys/vals:", dict(zip([c[1] for c in cols], row)))
    conn.close()
except Exception as e:
    print("Error:", e)

print("\n=== processed_messages.db ===")
try:
    conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", tables)
    for table in tables:
        tname = table[0]
        cols = conn.execute(f"PRAGMA table_info('{tname}')").fetchall()
        count = conn.execute(f"SELECT COUNT(*) FROM '{tname}'").fetchone()[0]
        print(f"Table '{tname}' ({count} rows):", [c[1] for c in cols])
    conn.close()
except Exception as e:
    print("Error:", e)
