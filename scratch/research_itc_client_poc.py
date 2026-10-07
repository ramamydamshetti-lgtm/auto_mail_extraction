import sqlite3
import json
import csv
import os

print("=== RESEARCHING ITC INFOTECH CLIENT POC & EMAIL ADDRESSES ===")

itc_pocs = {}

# 1. Search metaforge_requirements.db
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE lower(payload_json) LIKE '%itc%'").fetchall()
    print(f"\n1. Found {len(rows)} ITC rows in metaforge_requirements.db")
    for r in rows:
        try:
            p = json.loads(r[1])
            lead_poc = p.get("client_lead_poc")
            client_poc = p.get("client_poc")
            sender = p.get("sender_email") or p.get("from_email")
            
            for poc in [lead_poc, client_poc, sender]:
                if poc and poc != "None":
                    itc_pocs[poc] = itc_pocs.get(poc, 0) + 1
        except Exception:
            pass
    conn.close()

# 2. Search requirement_memory in processed_messages.db
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT id, requirement_from, payload_json FROM requirement_memory WHERE lower(requirement_from) LIKE '%itc%'").fetchall()
    print(f"\n2. Found {len(rows)} ITC rows in requirement_memory")
    for r in rows:
        try:
            p = json.loads(r[2])
            lead_poc = p.get("client_lead_poc")
            client_poc = p.get("client_poc")
            sender = p.get("sender_email") or p.get("from_email")
            
            for poc in [lead_poc, client_poc, sender]:
                if poc and poc != "None":
                    itc_pocs[poc] = itc_pocs.get(poc, 0) + 1
        except Exception:
            pass
    conn.close()

# 3. Search latest_500_all.csv
if os.path.exists("latest_500_all.csv"):
    with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        itc_csv_count = 0
        for row in reader:
            sender = row.get("from_email") or ""
            domain = row.get("sender_domain") or ""
            subj = row.get("subject") or ""
            if "itcinfotech.com" in sender or "itcinfotech.com" in domain or "itc" in subj.lower():
                itc_csv_count += 1
                if sender:
                    itc_pocs[sender] = itc_pocs.get(sender, 0) + 1
        print(f"\n3. Found {itc_csv_count} ITC messages in latest_500_all.csv")

print("\n=== TOP ITC CLIENT POC / SENDER EMAILS FOUND ===")
for email, count in sorted(itc_pocs.items(), key=lambda x: x[1], reverse=True):
    print(f"  - {email} -> {count} times")
