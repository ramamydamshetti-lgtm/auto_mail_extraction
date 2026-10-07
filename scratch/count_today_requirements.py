import sys
import os
import sqlite3
import json
import glob
sys.path.insert(0, os.path.abspath("."))
from ui.db import fetch_all_records

cfg = json.load(open("ui/config.json"))
all_recs = fetch_all_records(cfg)

today_str = "2026-09-29"

today_recs = []
for r in all_recs:
    created = str(r.get("created_at") or "")
    payload = r.get("payload") or {}
    demand_date = str(payload.get("demand_received_date") or "")
    
    if today_str in created or today_str in demand_date or "sep 29, 2026" in created.lower() or "sep 29, 2026" in demand_date.lower():
        today_recs.append(r)

print(f"=== TOTAL REQUIREMENTS FOR TODAY ({today_str}) ===")
print(f"Count: {len(today_recs)}")

print("\n=== BREAKDOWN BY CLIENT ===")
client_counts = {}
for r in today_recs:
    c = r.get("payload", {}).get("requirement_from") or "Other"
    client_counts[c] = client_counts.get(c, 0) + 1

for c, count in client_counts.items():
    print(f"  {c}: {count}")

print("\n=== SAMPLE TODAY REQUIREMENTS ===")
for i, r in enumerate(today_recs[:10]):
    p = r.get("payload", {})
    print(f"{i+1}. {r.get('req_id')} | Client: {p.get('requirement_from')} | Role: {p.get('job_title')} | Status: {p.get('job_status')}")
