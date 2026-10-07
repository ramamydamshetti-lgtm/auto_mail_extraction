import csv
import sqlite3
import json

print("=== CROSS REFERENCING PENDING REVIEWS WITH TODAY_FETCH.CSV ===")

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%'")
pr_rows = c_pm.fetchall()

email_map = {}
with open("today_fetch.csv", "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    for row in reader:
        gid = row.get("graph_id") or ""
        email_map[gid] = row

print(f"Loaded {len(email_map)} emails from today_fetch.csv")

for pid, gid, jid, cjd, pjson, ca in pr_rows[:6]:
    p = json.loads(pjson)
    print("="*80)
    print(f"PENDING REVIEW ID: {pid} | JOB ID: {jid}")
    print(f"EXTRACTED JOB TITLE : {p.get('job_title')}")
    print(f"EXTRACTED LOCATION  : {p.get('location')}")
    print(f"EXTRACTED SKILLS    : {p.get('mandatory_skills')}")
    print(f"EXTRACTED EXP       : {p.get('overall_experience')}")
    
    source_email = email_map.get(gid)
    if source_email:
        print("\nSOURCE EMAIL DETAILS:")
        print(f"  Subject : {source_email.get('subject')}")
        print(f"  From    : {source_email.get('from_email')}")
        body_snip = source_email.get('body_normalized') or source_email.get('body_plain') or ""
        print(f"  Body (first 400 chars):\n{body_snip[:400]}")
    else:
        print(f"\nSOURCE EMAIL NOT FOUND for graph_id: {gid}")
    print()

conn_pm.close()
