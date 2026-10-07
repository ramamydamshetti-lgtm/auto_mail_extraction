import sqlite3

conn = sqlite3.connect('data/metaforge_requirements.db')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables in metaforge_requirements.db:', tables)
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {count} rows")

cur = conn.execute("PRAGMA table_info(metaforge_requirements)")
print("metaforge_requirements columns:", [r[1] for r in cur.fetchall()])
