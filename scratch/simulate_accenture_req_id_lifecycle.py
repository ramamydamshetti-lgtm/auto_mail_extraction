import json
import csv
import sqlite3
import os
from datetime import datetime
from collections import defaultdict

# Script to simulate Rule Set 5 (Req ID identity and lifecycle with status_history tracking)

# 1. Gather all Accenture table rows from available datasets
accenture_rows = []

# Load from latest_500_all.json
if os.path.exists("latest_500_all.json"):
    with open("latest_500_all.json", "r", encoding="utf-8", errors="ignore") as f:
        items = json.load(f)
        for item in items:
            meta = item.get("metadata") or {}
            sender = str(meta.get("from") or item.get("from") or "").lower()
            subj = str(item.get("subject") or meta.get("subject") or "")
            body = str(item.get("content") or item.get("body") or "")
            ts = meta.get("received_date_time") or item.get("received_date_time") or "2026-09-28T10:00:00Z"
            
            # Check if Accenture email
            if "accenture" in sender or "iexcel" in sender or "accenture" in subj.lower():
                # Check for requirement payload or rows
                req = item.get("requirement") or {}
                raw_id = req.get("client_jd_id") or req.get("job_id")
                if raw_id:
                    accenture_rows.append({
                        "req_id": str(raw_id).strip().upper(),
                        "timestamp": ts,
                        "status": str(req.get("job_status") or "Open").strip(),
                        "job_title": req.get("job_title") or "",
                        "location": req.get("location") or "",
                        "skills": req.get("mandatory_skills") or "",
                        "source": "latest_500_all.json"
                    })

# Load from SQLite database (requirement_memory and metaforge_requirements)
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    db_rows = cur.execute("SELECT id, payload_json, created_at FROM requirement_memory WHERE lower(requirement_from) LIKE '%accenture%' ORDER BY created_at ASC").fetchall()
    for r in db_rows:
        try:
            p = json.loads(r[1])
            raw_id = p.get("client_jd_id") or p.get("job_id") or f"MEM-{r[0]}"
            accenture_rows.append({
                "req_id": str(raw_id).strip().upper(),
                "timestamp": r[2],
                "status": str(p.get("job_status") or "Open").strip(),
                "job_title": p.get("job_title") or "",
                "location": p.get("location") or "",
                "skills": p.get("mandatory_skills") or "",
                "source": "requirement_memory"
            })
        except Exception:
            pass
    conn.close()

if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    cur = conn.cursor()
    db_rows = cur.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE lower(payload_json) LIKE '%accenture%' ORDER BY created_at ASC").fetchall()
    for r in db_rows:
        try:
            p = json.loads(r[1])
            raw_id = p.get("client_jd_id") or p.get("job_id") or r[0]
            accenture_rows.append({
                "req_id": str(raw_id).strip().upper(),
                "timestamp": r[2],
                "status": str(p.get("job_status") or "Open").strip(),
                "job_title": p.get("job_title") or "",
                "location": p.get("location") or "",
                "skills": p.get("mandatory_skills") or "",
                "source": "metaforge_requirements"
            })
        except Exception:
            pass
    conn.close()

# Sort all rows by timestamp ASC
accenture_rows.sort(key=lambda x: str(x["timestamp"]))

print(f"=== TOTAL ACCENTURE ROWS TO PROCESS IN CHRONOLOGICAL ORDER: {len(accenture_rows)} ===")

# State Tracking Engine for Rule Set 5
req_store = {}
status_history = defaultdict(list)

counts = {
    "create": 0,
    "skip": 0,
    "update_status": 0,
    "update_content": 0
}

for row in accenture_rows:
    req_id = row["req_id"]
    new_status = row["status"]
    ts = row["timestamp"]
    content_hash = f"{row['job_title']}|{row['location']}|{row['skills']}"
    
    if req_id not in req_store:
        # 1. Not seen before -> Create
        req_store[req_id] = {
            "first_seen_at": ts,
            "last_seen_at": ts,
            "times_seen": 1,
            "last_status": new_status,
            "last_content_hash": content_hash
        }
        counts["create"] += 1
        # Log initial creation in status history
        status_history[req_id].append({
            "from_status": None,
            "to_status": new_status,
            "changed_at": ts,
            "action": "CREATED"
        })
    else:
        # Seen before
        record = req_store[req_id]
        record["last_seen_at"] = ts
        record["times_seen"] += 1
        
        old_status = record["last_status"]
        old_hash = record["last_content_hash"]
        
        if old_status != new_status:
            # 2. Status changed -> update_status with history tracking
            status_history[req_id].append({
                "from_status": old_status,
                "to_status": new_status,
                "changed_at": ts,
                "action": "UPDATE_STATUS"
            })
            record["last_status"] = new_status
            record["last_content_hash"] = content_hash
            counts["update_status"] += 1
        elif old_hash != content_hash:
            # 3. Status same, but content changed -> update_content
            record["last_content_hash"] = content_hash
            counts["update_content"] += 1
        else:
            # 4. Same status and content -> skip (touch timestamps & times_seen only)
            counts["skip"] += 1

# Analyze multi-flip requirements
flipped_reqs = {rid: history for rid, history in status_history.items() if len([h for h in history if h["action"] == "UPDATE_STATUS"]) >= 1}
multi_flipped_reqs = {rid: history for rid, history in status_history.items() if len([h for h in history if h["action"] == "UPDATE_STATUS"]) > 1}

print("\n=== RULE SET 5 SIMULATION COUNTS FOR ACCENTURE ===")
print(f"Total Unique Req IDs: {len(req_store)}")
print(f"  - CREATE (New Req IDs): {counts['create']}")
print(f"  - SKIP (Unchanged rows): {counts['skip']}")
print(f"  - UPDATE_STATUS (Status changed open<->hold): {counts['update_status']}")
print(f"  - UPDATE_CONTENT (Content updated, status same): {counts['update_content']}")

print(f"\nDistinct Req IDs that changed status at least once: {len(flipped_reqs)}")
print(f"Distinct Req IDs that flipped status MORE THAN ONES: {len(multi_flipped_reqs)}")

print("\n=== FULL STATUS TIMELINE FOR 5 SAMPLE REQ IDs ===")
sample_ids = list(status_history.keys())[:5]

for idx, rid in enumerate(sample_ids):
    print(f"\nSample {idx+1}: Req ID: {rid}")
    print(f"  Total Times Seen: {req_store[rid]['times_seen']}")
    print(f"  First Seen: {req_store[rid]['first_seen_at']} | Last Seen: {req_store[rid]['last_seen_at']}")
    print(f"  Current Status: {req_store[rid]['last_status']}")
    print("  Status Change Timeline:")
    for event in status_history[rid]:
        if event["action"] == "CREATED":
            print(f"    - [{event['changed_at']}] CREATED with initial status '{event['to_status']}'")
        else:
            print(f"    - [{event['changed_at']}] UPDATE_STATUS: '{event['from_status']}' --> '{event['to_status']}'")
