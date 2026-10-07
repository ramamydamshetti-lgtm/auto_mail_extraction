import sys
import os
import json
from collections import Counter
sys.path.insert(0, os.path.abspath("."))
from ui.db import fetch_all_records

cfg = json.load(open("ui/config.json"))
all_recs = fetch_all_records(cfg)

created_dates = Counter()
demand_dates = Counter()

for r in all_recs:
    c = str(r.get("created_at") or "")[:10]
    p = r.get("payload") or {}
    d = str(p.get("demand_received_date") or "")[:10]
    created_dates[c] += 1
    demand_dates[d] += 1

print("=== TOP CREATED DATES IN DB ===")
for d, count in created_dates.most_common(15):
    print(f"  Created Date: '{d}' -> {count} records")

print("\n=== TOP DEMAND RECEIVED DATES IN PAYLOAD ===")
for d, count in demand_dates.most_common(15):
    print(f"  Demand Date: '{d}' -> {count} records")
