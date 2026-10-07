import sqlite3
import json

conn = sqlite3.connect("data/processed_messages.db")
cur = conn.cursor()

rows = cur.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, review_fields, created_at FROM pending_reviews").fetchall()

print(f"Total items in pending_reviews: {len(rows)}")

ltts_pending = []
acc_pending = []
other_pending = []

for r in rows:
    p = json.loads(r[4])
    rf = str(p.get("requirement_from") or "").lower()
    title = str(p.get("job_title") or "")
    rev = r[5]
    req_id = p.get("client_jd_id") or p.get("job_id") or r[3]
    
    if "ltts" in rf or "ltts" in str(p).lower():
        ltts_pending.append((req_id, title, rev, r[6]))
    elif "accenture" in rf or "iexcel" in str(p).lower():
        acc_pending.append((req_id, title, rev, r[6]))
    else:
        other_pending.append((req_id, rf, title, rev, r[6]))

print(f"\n--- LTTS Requirements in Pending Review ({len(ltts_pending)}) ---")
for idx, (rid, title, rev, ca) in enumerate(ltts_pending, 1):
    print(f"  {idx}. Req ID: {rid} | Reason: {rev} | Date: {ca}")
    print(f"     Title: {title}")

print(f"\n--- Accenture Requirements in Pending Review ({len(acc_pending)}) ---")
for idx, (rid, title, rev, ca) in enumerate(acc_pending, 1):
    print(f"  {idx}. Req ID: {rid} | Reason: {rev} | Date: {ca}")
    print(f"     Title: {title}")

conn.close()
