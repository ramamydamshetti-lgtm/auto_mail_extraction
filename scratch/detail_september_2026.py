import sqlite3
import json

print("=== DETAILED BREAKDOWN FOR SEPTEMBER 2026 ===")

conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, requirement_from, payload_json, created_at FROM requirement_memory WHERE created_at LIKE '2026-09%'").fetchall()

accenture_list = []
ltts_list = []

for r in rows:
    p = json.loads(r["payload_json"])
    client = p.get("requirement_from") or r["requirement_from"]
    title = p.get("job_title", "N/A")
    req_id = p.get("client_jd_id") or p.get("job_id") or f"MEM-{r['id']}"
    date = r["created_at"][:10]
    loc = p.get("location", "N/A")
    status = p.get("job_status", "Open")

    item = {"req_id": req_id, "title": title, "date": date, "location": loc, "status": status}
    if "accenture" in client.lower():
        accenture_list.append(item)
    elif "ltts" in client.lower():
        ltts_list.append(item)

conn.close()

print(f"\nACCENTURE (Total in September 2026: {len(accenture_list)})")
for idx, a in enumerate(accenture_list, 1):
    print(f"{idx:2d}. Date: {a['date']} | Req ID: {a['req_id']} | Title: {a['title']} | Loc: {a['location']}")

print(f"\nLTTS (Total in September 2026: {len(ltts_list)})")
for idx, l in enumerate(ltts_list, 1):
    print(f"{idx:2d}. Date: {l['date']} | Req ID: {l['req_id']} | Title: {l['title']} | Loc: {l['location']}")
