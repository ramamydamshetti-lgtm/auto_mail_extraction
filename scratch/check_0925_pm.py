import sqlite3

conn = sqlite3.connect('data/processed_messages.db')
cursor = conn.cursor()
tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables in processed_messages.db:", tables)

for tbl in ["client_requirements", "pending_reviews", "requirement_memory"]:
    if tbl in tables:
        rows = cursor.execute(f"SELECT * FROM {tbl} WHERE client_jd_id LIKE '2026/09/25%' OR client_jd_id LIKE '2026-09-25%'").fetchall()
        print(f"{tbl} rows for 09/25: {len(rows)}")
        for r in rows[:10]:
            print("  ", r[0], r[1] if len(r)>1 else "")
conn.close()
