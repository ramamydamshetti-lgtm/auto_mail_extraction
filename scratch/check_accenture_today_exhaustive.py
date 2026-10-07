import sqlite3
import json
import os
import glob
from datetime import datetime

print("=== EXHAUSTIVE CHECK FOR ACCENTURE REQUIREMENTS TODAY (2026-09-29) ===")

target_date = "2026-09-29"

# 1. Check data/metaforge_requirements.db
print("\n--- 1. metaforge_requirements.db ---")
try:
    conn = sqlite3.connect("data/metaforge_requirements.db")
    rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
    acc_today = []
    for jid, ca, pjson in rows:
        p = json.loads(pjson)
        req_from = str(p.get("requirement_from") or "").lower()
        client_poc = str(p.get("client_lead_poc_email") or p.get("client_poc") or "").lower()
        title = str(p.get("job_title") or "")
        created = str(ca)
        demand_date = str(p.get("demand_received_date") or "")
        
        is_accenture = "accenture" in req_from or "iexcel.co.in" in client_poc or "anusha" in client_poc or "ACC" in jid
        is_today = target_date in created or target_date in demand_date or "sep 29" in demand_date.lower()
        
        if is_accenture and is_today:
            acc_today.append((jid, p.get("client_jd_id"), title, p.get("job_status"), created, demand_date))
            
    print(f"Total Accenture requirements created/received today: {len(acc_today)}")
    for idx, item in enumerate(acc_today, 1):
        print(f"  {idx}. Job ID: {item[0]} | Client JD ID: {item[1]} | Status: {item[3]} | Created: {item[4]}")
        print(f"     Title: {item[2]}")
    conn.close()
except Exception as e:
    print("Error:", e)

# 2. Check pending_reviews table in processed_messages.db
print("\n--- 2. pending_reviews table (data/processed_messages.db) ---")
try:
    conn = sqlite3.connect("data/processed_messages.db")
    rows = conn.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, review_fields, created_at FROM pending_reviews").fetchall()
    pending_acc_today = []
    for r in rows:
        created = str(r[6])
        if target_date in created:
            p = json.loads(r[4])
            req_from = str(p.get("requirement_from") or "").lower()
            if "accenture" in req_from or "iexcel.co.in" in str(p).lower():
                pending_acc_today.append((r[2], r[3], p.get("job_title"), r[5], created))
    print(f"Total pending_review Accenture items today: {len(pending_acc_today)}")
    for idx, item in enumerate(pending_acc_today, 1):
        print(f"  {idx}. Job ID: {item[0]} | Client JD ID: {item[1]} | Reason: {item[3]}")
        print(f"     Title: {item[2]}")
    conn.close()
except Exception as e:
    print("Error:", e)

# 3. Check requirement_memory table in processed_messages.db
print("\n--- 3. requirement_memory table (data/processed_messages.db) ---")
try:
    conn = sqlite3.connect("data/processed_messages.db")
    rows = conn.execute("SELECT id, requirement_from, job_title_norm, payload_json, created_at FROM requirement_memory WHERE created_at LIKE '%2026-09-29%'").fetchall()
    mem_acc_today = []
    for r in rows:
        rf = str(r[1]).lower()
        if "accenture" in rf or "iexcel.co.in" in str(r[3]).lower():
            p = json.loads(r[3])
            mem_acc_today.append((p.get("job_id"), p.get("client_jd_id"), p.get("job_title"), p.get("job_status"), r[4]))
    print(f"Total requirement_memory Accenture items today: {len(mem_acc_today)}")
    for idx, item in enumerate(mem_acc_today, 1):
        print(f"  {idx}. Job ID: {item[0]} | Client JD ID: {item[1]} | Status: {item[3]}")
        print(f"     Title: {item[2]}")
    conn.close()
except Exception as e:
    print("Error:", e)

# 4. Check client_requirements table in data/processed.db or processed_store.db
print("\n--- 4. client_requirements table ---")
for db in ["data/processed.db", "processed.db", "data/processed_messages.db"]:
    if os.path.exists(db):
        try:
            conn = sqlite3.connect(db)
            has_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='client_requirements'").fetchone()
            if has_table:
                rows = conn.execute("SELECT client_jd_id, requirement_from, status, payload_json, updated_at FROM client_requirements").fetchall()
                print(f"  Found {len(rows)} total rows in {db} client_requirements")
                c_acc = []
                for r in rows:
                    if "accenture" in str(r[1]).lower() or "accenture" in str(r[3]).lower() or "iexcel" in str(r[3]).lower():
                        c_acc.append(r)
                print(f"  Accenture rows in client_requirements: {len(c_acc)}")
                for idx, r in enumerate(c_acc, 1):
                    p = json.loads(r[3])
                    print(f"    {idx}. Req ID: {r[0]} | Status: {r[2]} | Updated: {r[4]}")
                    print(f"       Title: {p.get('job_title')}")
            conn.close()
        except Exception as e:
            print(f"Error checking {db}: {e}")
