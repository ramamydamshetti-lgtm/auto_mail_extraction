import csv
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()
db_graph_ids = set(r[0] for r in cur.execute("SELECT graph_id FROM filtered_log WHERE subject LIKE '%accenture%'").fetchall())
db_pending_gids = set(r[0] for r in cur.execute("SELECT graph_id FROM pending_reviews").fetchall())
conn.close()

print(f"Total graph_ids in filtered_log: {len(db_graph_ids)}")

with open('latest_500_all.csv', mode='r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    found_filtered = 0
    found_pending = 0
    found_anusha = 0
    all_accenture_rows = []
    for idx, row in enumerate(reader):
        gid = row.get('graph_id')
        from_e = row.get('from_email')
        subj = row.get('subject')
        if gid in db_graph_ids:
            found_filtered += 1
        if gid in db_pending_gids:
            found_pending += 1
        if 'anusha' in from_e.lower() or 'accenture' in subj.lower() or 'accenture' in from_e.lower():
            found_anusha += 1
            all_accenture_rows.append((idx, gid, subj, from_e, row.get('body_normalized')))

print(f"Matched graph_ids in latest_500_all.csv from filtered_log: {found_filtered}")
print(f"Matched graph_ids in latest_500_all.csv from pending_reviews: {found_pending}")
print(f"Total Accenture/Anusha rows found in latest_500_all.csv: {found_anusha}")

for idx, gid, subj, from_e, body in all_accenture_rows[:5]:
    print(f"Row {idx} | GID={gid[:20]} | Subj={subj} | From={from_e}")
    print("Body snippet:")
    print(body[:300] if body else "EMPTY")
    print("-" * 50)
