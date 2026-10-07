import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("data/processed_messages.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- Date distribution in processed table ---")
dates = []
for r in cursor.execute("SELECT processed_at, payload_json FROM processed").fetchall():
    proc_at = (r["processed_at"] or "")[:10]
    payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
    dem_date = (payload.get("demand_received_date") or payload.get("receivedDateTime") or proc_at)[:10]
    dates.append(dem_date)

date_counts = Counter(dates)
for d, count in sorted(date_counts.items(), reverse=True)[:15]:
    print(f"  {d}: {count} requirements")

print("\n--- Date distribution in pending_reviews table ---")
pending_dates = []
for r in cursor.execute("SELECT created_at, payload_json FROM pending_reviews").fetchall():
    created = (r["created_at"] or "")[:10]
    payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
    dem_date = (payload.get("demand_received_date") or payload.get("receivedDateTime") or created)[:10]
    pending_dates.append(dem_date)

p_counts = Counter(pending_dates)
for d, count in sorted(p_counts.items(), reverse=True)[:15]:
    print(f"  {d}: {count} pending reviews")

conn.close()
