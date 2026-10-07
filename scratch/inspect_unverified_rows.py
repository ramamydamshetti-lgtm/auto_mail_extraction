import sqlite3
import json

conn = sqlite3.connect("data/metaforge_requirements.db")
c = conn.cursor()

# Find rows where sender is empty or missing, or bodyText is empty
rows = c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements").fetchall()

empty_sender = []
empty_body = []
all_senders = set()

for r in rows:
    p = json.loads(r[2]) if r[2] else {}
    sender = p.get("from") or p.get("client_poc") or p.get("client_lead_poc") or ""
    body = p.get("bodyText") or p.get("bodyHtml") or ""
    all_senders.add(sender)
    
    if not sender.strip():
        empty_sender.append((r[0], r[1], p))
    if not body.strip():
        empty_body.append((r[0], r[1], p))

print(f"Total rows: {len(rows)}")
print(f"Rows with empty sender: {len(empty_sender)}")
for j, cjd, p in empty_sender:
    print(f"  Job ID: {j} | Client ID: {cjd}")
    print(f"    Subject: {p.get('subject')}")
    print(f"    Company: {p.get('requirement_from')}")
    print(f"    Body snippet: {str(p.get('bodyText', ''))[:200]}")

print(f"\nRows with empty body: {len(empty_body)}")
print(f"\nDistinct senders across all 236 rows ({len(all_senders)}):")
for s in sorted(all_senders):
    print(f"  - '{s}'")
