import sqlite3
import json

print("=== INSPECTING ACCENTURE DEMANDS FOR SEP 28 / SEP 29 ===")

conn = sqlite3.connect("data/processed_messages.db")
cur = conn.cursor()

rows = cur.execute("SELECT id, requirement_from, job_title_norm, payload_json, created_at FROM requirement_memory WHERE lower(requirement_from) LIKE '%accenture%' ORDER BY created_at DESC LIMIT 20").fetchall()

print(f"\nTotal Accenture records in requirement_memory: {len(rows)}")
for idx, r in enumerate(rows):
    try:
        p = json.loads(r[3])
        print(f"\n{idx+1}. ID: MEM-{r[0]} | Req ID: {p.get('client_jd_id') or p.get('job_id')} | Date: {p.get('demand_received_date') or r[4][:10]}")
        print(f"   Title: {p.get('job_title')}")
        print(f"   Status: {p.get('job_status')} | Priority: {p.get('priority')} | Location: {p.get('location')}")
        print(f"   Skills: {p.get('mandatory_skills')}")
    except Exception as e:
        print("Error reading payload:", e)
