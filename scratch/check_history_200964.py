import sqlite3, json

conn = sqlite3.connect('data/processed_messages.db')
conn.row_factory = sqlite3.Row

print("Checking processed_messages.db:")
for tbl in ['processed', 'pending_reviews', 'client_requirements', 'filtered_logs', 'requirement_memory']:
    try:
        rows = conn.execute(f'SELECT * FROM {tbl}').fetchall()
        matches = 0
        for r in rows:
            blob = json.dumps(dict(r))
            if '200964-1' in blob:
                matches += 1
        print(f"  Table {tbl}: {matches} matches")
    except Exception as e:
        print(f"  Table {tbl}: error {e}")
