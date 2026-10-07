import sqlite3

conn = sqlite3.connect("data/processed_messages.db")
cursor = conn.cursor()

tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Checking tables in data/processed_messages.db: {tables}")

for t in tables:
    count_all = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    # Check if string 2026-09-30 is anywhere in rows
    rows = cursor.execute(f"SELECT * FROM {t}").fetchall()
    cnt_30 = 0
    for r in rows:
        if "2026-09-30" in str(r) or "30/09/2026" in str(r):
            cnt_30 += 1
    print(f"Table '{t}': Total rows = {count_all}, matching 30/09/2026 = {cnt_30}")

conn.close()
