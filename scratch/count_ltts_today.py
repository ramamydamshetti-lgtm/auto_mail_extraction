import sqlite3
import json
import os
import csv

target_date = "2026-09-29"

print(f"=== CHECKING LTTS REQUIREMENTS FOR {target_date} ===")

# 1. Check metaforge_requirements.db
ltts_metaforge = []
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
    for jid, ca, pjson in rows:
        p = json.loads(pjson)
        req_from = str(p.get("requirement_from") or "").lower()
        poc = str(p.get("client_lead_poc_email") or p.get("client_poc") or "").lower()
        title = str(p.get("job_title") or "")
        created = str(ca)
        demand_date = str(p.get("demand_received_date") or "")
        
        is_ltts = "ltts" in req_from or "ltts.com" in poc or "l&t" in req_from or "LTTS" in jid
        is_today = target_date in created or target_date in demand_date or "sep 29, 2026" in demand_date.lower() or "29-sep-2026" in demand_date.lower()
        
        if is_ltts and is_today:
            ltts_metaforge.append((jid, p.get("client_jd_id"), title, p.get("job_status"), created, demand_date))
    conn.close()

print(f"\n1. In metaforge_requirements.db: {len(ltts_metaforge)}")
for idx, r in enumerate(ltts_metaforge, 1):
    print(f"   {idx}. Job ID: {r[0]} | Req ID: {r[1]} | Status: {r[3]} | Created: {r[4]}")
    print(f"      Title: {r[2]}")

# 2. Check all LTTS records created in September 2026 for context
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
    sept_ltts = []
    for jid, ca, pjson in rows:
        p = json.loads(pjson)
        rf = str(p.get("requirement_from") or "").lower()
        if "ltts" in rf or "l&t" in rf or "LTTS" in jid:
            sept_ltts.append((jid, ca, p.get("job_title")))
    print(f"\n2. Total LTTS records in database across September 2026: {len(sept_ltts)}")
    conn.close()
