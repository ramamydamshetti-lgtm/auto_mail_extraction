import sqlite3
import json
from collections import defaultdict

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT id, graph_id, job_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%' AND (lower(payload_json) LIKE '%ltts%' OR lower(payload_json) LIKE '%l&t%')")
pr_rows = c_pm.fetchall()

by_email = defaultdict(list)
for pid, gid, jid, pjson, ca in pr_rows:
    p = json.loads(pjson)
    by_email[gid].append((pid, jid, p))

print(f"Total Emails that produced LTTS requirements: {len(by_email)}")
print(f"Total Extracted LTTS Items across these emails: {len(pr_rows)}\n")

for gid, items in by_email.items():
    print("="*80)
    print(f"EMAIL GRAPH ID: {gid}")
    print(f"Extracted Items Count from this single email: {len(items)}")
    for pid, jid, p in items:
        print(f"  - [Pending Review ID {pid} | {jid}] Title: '{p.get('job_title')}' | Location: '{p.get('location')}'")

conn_pm.close()
