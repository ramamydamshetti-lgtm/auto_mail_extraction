import sqlite3
import json
from collections import Counter, defaultdict

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()

c.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE created_at LIKE '2026-09-29%'")
rows = c.fetchall()

print("======================================================================")
print(f"COMPLETE SENDER ANALYSIS FOR TODAY'S (29/09/2026) REQUIREMENTS ({len(rows)} TOTAL)")
print("======================================================================")

by_client_sender = defaultdict(list)

for jid, pjson in rows:
    p = json.loads(pjson)
    client = p.get('requirement_from') or 'Other'
    sender = p.get('client_lead_poc') or p.get('client_poc') or p.get('client_lead_poc_email') or 'Unknown'
    cjd = p.get('client_jd_id') or jid
    title = p.get('job_title') or 'N/A'
    by_client_sender[client].append((cjd, sender, title))

for client, items in by_client_sender.items():
    print(f"\nCLIENT: {client.upper()} ({len(items)} Requirements)")
    print("-" * 70)
    
    sender_counts = Counter(item[1] for item in items)
    for sender_email, count in sender_counts.items():
        print(f"  • Sender: {sender_email:45s} | Requirements: {count}")
    
    print("\n  Detailed Requirement List:")
    for cjd, sender_email, title in items:
        print(f"    - [Req ID: {cjd:24s}] {title} (Sender: {sender_email})")

conn.close()
