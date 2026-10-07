import csv
import json
import sqlite3
import os

print("=== LOCATING REAL ACCENTURE SAMPLE EMAIL TEXT ===")

# Check today_fetch.csv for Accenture emails
if os.path.exists("today_fetch.csv"):
    with open("today_fetch.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            subj = str(row.get("subject") or "")
            body = str(row.get("body_normalized") or row.get("body_plain") or "")
            sender = str(row.get("from_email") or "")
            if "accenture" in subj.lower() or "accenture" in body.lower() or "iexcel" in sender.lower() or "anusha" in sender.lower():
                print(f"\n--- Real Accenture Email #{idx+1} ---")
                print(f"From: {sender}")
                print(f"Subject: {subj}")
                print(f"Body snippet:\n{body[:600]}")
                break

# Check metaforge_requirements.db
conn = sqlite3.connect("data/metaforge_requirements.db")
rows = conn.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE lower(payload_json) LIKE '%accenture%' OR lower(payload_json) LIKE '%iexcel%' LIMIT 1").fetchall()
if rows:
    p = json.loads(rows[0][1])
    prov = p.get("_provenance", {})
    print("\n--- Real Database Ingest Record Payload ---")
    print(f"Job ID: {rows[0][0]}")
    print(f"Subject: {prov.get('email_subject')}")
    print(f"Body text:\n{str(p.get('email_body_plain') or prov.get('body_text') or p.get('job_title'))[:600]}")
conn.close()
