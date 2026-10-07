import json
import sqlite3
import csv

print("=== Checking pending_reviews table ===")
conn = sqlite3.connect("data/processed_messages.db")
cur = conn.cursor()

rows = cur.execute("SELECT job_id, client_jd_id, payload_json FROM pending_reviews WHERE lower(payload_json) LIKE '%accenture%29th%' OR lower(payload_json) LIKE '%accenture open demands%'").fetchall()

print(f"Found {len(rows)} matching rows in pending_reviews")
for r in rows[:10]:
    print(f"Job ID: {r[0]} | Client JD ID: {r[1]}")
    try:
        p = json.loads(r[2])
        print("  Title:", p.get("job_title"))
        print("  Demand date:", p.get("demand_received_date"))
        print("  Skills:", p.get("mandatory_skills"))
    except Exception:
        pass

print("\n=== Checking latest_500_all.json for 'Accenture open demands for 29th Sep' ===")
with open("latest_500_all.json", "r", encoding="utf-8", errors="ignore") as f:
    data = json.load(f)
    for item in data:
        subj = str(item.get("subject") or item.get("metadata", {}).get("subject") or "")
        if "accenture open demands" in subj.lower() or "29th sep" in subj.lower():
            print("\nFound Email Subject:", subj)
            content = str(item.get("content") or item.get("body") or "")
            print("Snippet:", content[:600].replace("\n", " "))
