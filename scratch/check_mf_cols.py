import sqlite3

conn = sqlite3.connect("data/metaforge_requirements.db")
cursor = conn.cursor()

tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables in metaforge_requirements.db:", tables)

for t in tables:
    cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({t})").fetchall()]
    print(f"Table '{t}' columns:", cols)

conn.close()
