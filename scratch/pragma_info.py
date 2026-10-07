import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()

for tbl in ['filtered_log', 'pending_reviews', 'requirement_memory']:
    print(f"=== {tbl} columns ===")
    cur.execute(f"PRAGMA table_info({tbl})")
    cols = [r[1] for r in cur.fetchall()]
    print(cols)

conn.close()
