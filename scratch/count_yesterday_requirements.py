import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from ui.db import fetch_all_records

print("=== COUNT OF REQUIREMENTS RECEIVED YESTERDAY (2026-09-28) ===")

yesterday_str = "2026-09-28"

cfg = json.load(open("ui/config.json"))
all_recs = fetch_all_records(cfg)

yesterday_recs = []

for r in all_recs:
    created = str(r.get("created_at") or "")
    payload = r.get("payload") or {}
    demand_date = str(payload.get("demand_received_date") or "")
    
    if yesterday_str in created or yesterday_str in demand_date or "sep 28, 2026" in created.lower() or "sep 28, 2026" in demand_date.lower():
        yesterday_recs.append(r)

print(f"\nTotal Unique Requirements Yesterday ({yesterday_str}): {len(yesterday_recs)}")

print("\n--- Breakdown by Client ---")
client_counts = {}
for r in yesterday_recs:
    c = r.get("payload", {}).get("requirement_from") or "Other"
    client_counts[c] = client_counts.get(c, 0) + 1

for c, count in sorted(client_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  - {c}: {count}")

print("\n--- Sample Requirements Yesterday ---")
for idx, r in enumerate(yesterday_recs[:15], 1):
    p = r.get("payload", {})
    print(f"{idx}. {r.get('req_id')} | Client: {p.get('requirement_from')} | Role: {p.get('job_title')} | Status: {p.get('job_status')}")
