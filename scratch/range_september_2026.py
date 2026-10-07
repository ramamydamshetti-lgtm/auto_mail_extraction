import sqlite3
import json

print("=== EXACT DATE FILTER: 2026-09-01 to 2026-09-28 ===")

conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# Query requirement_memory
rows = conn.execute("""
    SELECT id, requirement_from, payload_json, created_at 
    FROM requirement_memory 
    WHERE DATE(created_at) >= '2026-09-01' AND DATE(created_at) <= '2026-09-28'
""").fetchall()

accenture_reqs = []
ltts_reqs = []
other_reqs = []

for r in rows:
    p = json.loads(r["payload_json"])
    client = (p.get("requirement_from") or r["requirement_from"] or "").lower()
    date_str = r["created_at"][:10]
    title = p.get("job_title", "N/A")
    req_id = p.get("client_jd_id") or p.get("job_id") or f"MEM-{r['id']}"
    
    entry = {"date": date_str, "req_id": req_id, "title": title, "client": client}

    if "accenture" in client or "iexcel" in client:
        accenture_reqs.append(entry)
    elif "ltts" in client or "l&t" in client:
        ltts_reqs.append(entry)
    else:
        other_reqs.append(entry)

conn.close()

print(f"Accenture (Sept 1 to Sept 28, 2026): {len(accenture_reqs)}")
print(f"LTTS (Sept 1 to Sept 28, 2026): {len(ltts_reqs)}")
print(f"Other Clients (Sept 1 to Sept 28, 2026): {len(other_reqs)}")
print(f"TOTAL REQUIREMENTS (Sept 1 to Sept 28, 2026): {len(accenture_reqs) + len(ltts_reqs) + len(other_reqs)}")

# Group by date for Accenture and LTTS
print("\n--- Daily Breakdown (Sept 1 to Sept 28, 2026) ---")
dates = sorted(list({r['date'] for r in accenture_reqs + ltts_reqs}))
for d in dates:
    acc_c = sum(1 for r in accenture_reqs if r['date'] == d)
    ltts_c = sum(1 for r in ltts_reqs if r['date'] == d)
    print(f"Date {d}: Accenture = {acc_c}, LTTS = {ltts_c}, Daily Combined = {acc_c + ltts_c}")
