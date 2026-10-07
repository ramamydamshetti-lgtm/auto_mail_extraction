import sqlite3
import json
from collections import Counter, defaultdict

print("======================================================================")
print("TODAY'S (2026-09-29) EXHAUSTIVE REQUIREMENT BREAKDOWN BY CLIENT")
print("======================================================================")

# 1. Check metaforge_requirements.db (Active Synced)
conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()
c_mr.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE created_at LIKE '2026-09-29%'")
mr_rows = c_mr.fetchall()

mr_by_client = defaultdict(list)
for jid, pjson, ca in mr_rows:
    p = json.loads(pjson)
    client = p.get('requirement_from') or 'Unknown'
    mr_by_client[client].append((jid, p))
conn_mr.close()

# 2. Check pending_reviews in processed_messages.db
conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()
c_pm.execute("SELECT id, job_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%'")
pr_rows = c_pm.fetchall()

pr_by_client = defaultdict(list)
for pid, jid, pjson, ca in pr_rows:
    p = json.loads(pjson)
    client = p.get('requirement_from') or 'Unknown'
    pr_by_client[client].append((pid, jid, p))
conn_pm.close()

all_clients = set(list(mr_by_client.keys()) + list(pr_by_client.keys()))

print(f"\nTOTAL CLIENTS INGESTED TODAY: {len(all_clients)}")
print(f"TOTAL ACTIVE SYNCED REQUIREMENTS  : {len(mr_rows)}")
print(f"TOTAL PENDING REVIEW REQUIREMENTS: {len(pr_rows)}")
print(f"COMBINED TOTAL EXTRACTED TODAY   : {len(mr_rows) + len(pr_rows)}\n")

for client in sorted(all_clients):
    active = mr_by_client[client]
    pending = pr_by_client[client]
    tot = len(active) + len(pending)
    print("="*70)
    print(f"CLIENT: {client.upper()} | Total Extracted Today: {tot} (Active: {len(active)}, Pending Review: {len(pending)})")
    print("="*70)
    if active:
        print("  Active Synced Requirements:")
        for jid, p in active:
            print(f"    - [{jid}] {p.get('job_title')} (Location: {p.get('location') or 'N/A'})")
    if pending:
        print("  Pending Review Requirements:")
        for pid, jid, p in pending:
            print(f"    - [Pending Review #{pid} | {jid}] {p.get('job_title')} (Location: {p.get('location') or 'N/A'})")
    print()
