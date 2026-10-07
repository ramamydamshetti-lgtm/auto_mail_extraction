import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# 1. requirement_memory
print("=== requirement_memory table date breakdown ===")
rows = conn.execute("SELECT created_at, payload_json FROM requirement_memory").fetchall()
rm_dates = Counter()
sept30_reqs = []

for r in rows:
    p = json.loads(r["payload_json"])
    d = (r["created_at"] or "")[:10]
    rm_dates[d] += 1
    if d == "2026-09-30":
        sept30_reqs.append(p)

for d, cnt in sorted(rm_dates.items(), reverse=True):
    print(f"  {d}: {cnt}")

print(f"\nTotal requirements on 2026-09-30 in requirement_memory: {len(sept30_reqs)}")

# 2. metaforge_requirements db
print("\n=== metaforge_requirements table date breakdown ===")
conn_mf = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
conn_mf.row_factory = sqlite3.Row
mf_rows = conn_mf.execute("SELECT created_at, payload_json FROM metaforge_requirements").fetchall()
mf_dates = Counter()
mf_sept30 = []
for r in mf_rows:
    p = json.loads(r["payload_json"]) if r["payload_json"] else {}
    d = (r["created_at"] or "")[:10]
    mf_dates[d] += 1
    if d == "2026-09-30":
        mf_sept30.append(p)

for d, cnt in sorted(mf_dates.items(), reverse=True):
    print(f"  {d}: {cnt}")

print(f"Total requirements on 2026-09-30 in metaforge_requirements: {len(mf_sept30)}")

conn.close()
conn_mf.close()
