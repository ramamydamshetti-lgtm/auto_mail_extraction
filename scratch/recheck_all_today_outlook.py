import sqlite3
import json
import glob
import os

target_date = "2026-09-29"

print(f"======================================================================")
print(f"COMPLETE EXHAUSTIVE RECHECK FOR ALL OUTLOOK REQUIREMENTS ON {target_date}")
print(f"======================================================================")

# 1. Active Synced Requirements in metaforge_requirements.db
print("\n[1] Active Synced Requirements (data/metaforge_requirements.db):")
synced_today = []
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
    for jid, ca, pjson in rows:
        p = json.loads(pjson)
        created = str(ca)
        demand_date = str(p.get("demand_received_date") or "")
        
        if target_date in created or target_date in demand_date or "sep 29, 2026" in demand_date.lower():
            synced_today.append((jid, p.get("client_jd_id"), p.get("requirement_from"), p.get("job_title"), p.get("job_status"), created))
    conn.close()

print(f"Total Synced Requirements Today: {len(synced_today)}")
for idx, r in enumerate(synced_today, 1):
    print(f"  {idx}. [{r[2]}] Job ID: {r[0]} | Req ID: {r[1]} | Status: {r[4]}")
    print(f"     Title: {r[3]}")
    print(f"     Timestamp: {r[5]}")

# 2. Pending Reviews (data/processed_messages.db)
print("\n[2] Pending Review Items (data/processed_messages.db):")
pending_today = []
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    rows = conn.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, review_fields, created_at FROM pending_reviews").fetchall()
    for r in rows:
        created = str(r[6])
        if target_date in created:
            p = json.loads(r[4])
            pending_today.append((r[2], r[3], p.get("requirement_from"), p.get("job_title"), r[5], created))
    conn.close()

print(f"Total Pending Review Items Today: {len(pending_today)}")
for idx, r in enumerate(pending_today, 1):
    print(f"  {idx}. [{r[2]}] Job ID: {r[0]} | Req ID: {r[1]} | Reason: {r[4]}")
    print(f"     Title: {r[3]}")

# 3. Filtered Log (data/processed_messages.db)
print("\n[3] Filtered/Blocked Messages Log Today (data/processed_messages.db):")
filtered_today = []
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    rows = conn.execute("SELECT graph_id, subject, from_email, reason, stage, created_at FROM filtered_log").fetchall()
    for r in rows:
        created = str(r[5])
        if target_date in created:
            filtered_today.append((r[0], r[1], r[2], r[3], r[4], created))
    conn.close()

print(f"Total Filtered Messages Today: {len(filtered_today)}")
for idx, r in enumerate(filtered_today, 1):
    print(f"  {idx}. From: {r[2]} | Stage: {r[4]} | Reason: {r[3]}")
    print(f"     Subject: {r[1]}")

# 4. Breakdown by Client Across All Stores Today
print("\n======================================================================")
print("TOTAL SUMMARY BREAKDOWN FOR TODAY (2026-09-29):")
print(f"  - Active Synced Requirements: {len(synced_today)}")
print(f"  - Pending Review Items:      {len(pending_today)}")
print(f"  - Blocked/Filtered Emails:    {len(filtered_today)}")
print("======================================================================")
