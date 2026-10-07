import sqlite3

conn = sqlite3.connect("data/processed_messages.db")
cursor = conn.cursor()

for table in ["processed", "pending_reviews", "pipeline_state"]:
    print(f"Table: {table}")
    cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    print("  Columns:", cols)

conn.close()
