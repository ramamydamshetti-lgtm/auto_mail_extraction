import sqlite3
import json
import csv
import glob
import os
import re

print("================ SEPTEMBER 2026 REQUIREMENTS ANALYSIS ================")

# Helper to check if text matches Accenture or LTTS
def match_client(text):
    if not text:
        return None
    t = str(text).lower()
    if "accenture" in t or "iexcel" in t:
        return "Accenture"
    if "ltts" in t or "l&t" in t:
        return "LTTS"
    return None

# Helper to check if date is September 2026
def is_september_2026(date_str):
    if not date_str:
        return False
    d = str(date_str)
    # Check for 2026-09 or Sep 2026 or September 2026
    if "2026-09" in d or "2026/09" in d or "Sep-2026" in d or "September 2026" in d or "Sep 2026" in d:
        return True
    return False

counts = {
    "Accenture": {"total": 0, "sep_2026": 0, "sources": {}},
    "LTTS": {"total": 0, "sep_2026": 0, "sources": {}}
}

# 1. Check SQLite metaforge_requirements.db
print("\n--- Checking metaforge_requirements.db ---")
try:
    conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements").fetchall()
    for r in rows:
        payload = json.loads(r["payload_json"])
        client = match_client(payload.get("requirement_from") or payload.get("client_poc") or "")
        created = r["created_at"]
        dem_date = payload.get("demand_received_date", "")
        if client:
            counts[client]["total"] += 1
            if is_september_2026(created) or is_september_2026(dem_date):
                counts[client]["sep_2026"] += 1
                print(f"[{client}] Match in metaforge_requirements: created={created}, demand_date={dem_date}, title={payload.get('job_title')}")
    conn.close()
except Exception as e:
    print("metaforge_requirements.db error:", e)

# 2. Check SQLite processed_messages.db (requirement_memory)
print("\n--- Checking processed_messages.db (requirement_memory) ---")
try:
    conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, requirement_from, payload_json, created_at FROM requirement_memory").fetchall()
    for r in rows:
        payload = json.loads(r["payload_json"])
        client = match_client(r["requirement_from"] or payload.get("requirement_from") or "")
        created = r["created_at"]
        dem_date = payload.get("demand_received_date", "")
        if client:
            counts[client]["total"] += 1
            if is_september_2026(created) or is_september_2026(dem_date):
                counts[client]["sep_2026"] += 1
                print(f"[{client}] Match in requirement_memory: created={created}, demand_date={dem_date}, title={payload.get('job_title')}")
    conn.close()
except Exception as e:
    print("processed_messages.db error:", e)

# 3. Check latest_500_all.csv
print("\n--- Checking latest_500_all.csv ---")
if os.path.exists("latest_500_all.csv"):
    with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = row.get("from_address") or row.get("sender") or ""
            subj = row.get("subject") or ""
            body = row.get("body") or ""
            date_str = row.get("received_date_time") or row.get("date") or ""
            client = match_client(sender) or match_client(subj) or match_client(body)
            if client and is_september_2026(date_str):
                print(f"[{client}] Match in latest_500_all.csv: date={date_str}, sender={sender}, subject={subj[:50]}")

# 4. Check all dates present in the SQLite DBs to report available date ranges
print("\n--- Date Range Summary in DBs ---")
try:
    conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
    dates = conn.execute("SELECT SUBSTR(created_at, 1, 7) as month, count(*) FROM requirement_memory GROUP BY month").fetchall()
    print("requirement_memory months:", dates)
    conn.close()
except Exception as e:
    print("Err:", e)

try:
    conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
    dates = conn.execute("SELECT SUBSTR(created_at, 1, 7) as month, count(*) FROM metaforge_requirements GROUP BY month").fetchall()
    print("metaforge_requirements months:", dates)
    conn.close()
except Exception as e:
    print("Err:", e)

print("\n================ FINAL COUNTS ================")
print(json.dumps(counts, indent=2))
