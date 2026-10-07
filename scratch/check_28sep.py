import sqlite3
import json

conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE DATE(created_at) = '2026-09-28'").fetchall()

print(f"Total Requirements Received/Recorded for 28/09/2026: {len(rows)}")

client_summary = {}

for idx, r in enumerate(rows, 1):
    p = json.loads(r["payload_json"])
    client = p.get("requirement_from", "Unknown")
    req_id = p.get("client_jd_id") or p.get("job_id")
    title = p.get("job_title", "N/A")
    action = p.get("action", "Registered")
    
    client_summary[client] = client_summary.get(client, 0) + 1
    print(f" {idx}. [{client}] Req ID: {req_id} | Title: {title} | Action: {action}")

conn.close()

print("\n--- CLIENT BREAKDOWN FOR 28/09/2026 ---")
for client, count in client_summary.items():
    print(f" • {client}: {count} requirements")
