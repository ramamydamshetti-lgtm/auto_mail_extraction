import sqlite3
import json

print("=== STEP 1: TIMEZONE & CURRENT SYSTEM DATE/TIME ===")
import datetime
now = datetime.datetime.now(datetime.timezone.utc)
local_now = datetime.datetime.now()
print(f"UTC Time: {now.isoformat()}")
print(f"Local System Time: {local_now.isoformat()}")

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables_pm = [r[0] for r in c_pm.fetchall()]
print("Tables in processed_messages.db:", tables_pm)

for t in tables_pm:
    c_pm.execute(f"PRAGMA table_info({t})")
    cols = [c[1] for c in c_pm.fetchall()]
    c_pm.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = c_pm.fetchone()[0]
    print(f"  Table '{t}' ({cnt} rows): {cols[:8]}")

conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()
c_mr.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables_mr = [r[0] for r in c_mr.fetchall()]
print("Tables in metaforge_requirements.db:", tables_mr)
for t in tables_mr:
    c_mr.execute(f"PRAGMA table_info({t})")
    cols = [c[1] for c in c_mr.fetchall()]
    c_mr.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = c_mr.fetchone()[0]
    print(f"  Table '{t}' ({cnt} rows): {cols[:8]}")
