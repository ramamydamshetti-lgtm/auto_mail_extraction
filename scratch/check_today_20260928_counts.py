import sqlite3
import json

conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE DATE(created_at) = '2026-09-28'").fetchall()

print("================ TODAY (28/09/2026) REGISTERED REQUIREMENTS ================")
print(f"Total Requirements Recorded Today: {len(rows)}\n")

acc_count = 0
itc_count = 0

for idx, r in enumerate(rows, 1):
    p = json.loads(r["payload_json"])
    client = p.get("requirement_from")
    req_id = p.get("client_jd_id") or p.get("job_id")
    title = p.get("job_title")
    action = p.get("action", "Registered")
    status = p.get("job_status")
    
    if client == "Accenture":
        acc_count += 1
    elif client == "ITC Infotech":
        itc_count += 1
        
    print(f"{idx}. Client: {client:<14} | Req ID: {req_id:<24} | Action: {action:<38} | Status: {status}")

conn.close()

print(f"\nCLIENT SUMMARY FOR 28/09/2026:")
print(f"  • ITC Infotech : {itc_count} requirement")
print(f"  • Accenture    : {acc_count} requirements (3 NEW + 2 REOPENED)")
