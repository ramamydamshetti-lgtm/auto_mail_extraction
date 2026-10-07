import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()

# Get all payloads from pending_reviews and filtered_log
pending_rows = cur.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json FROM pending_reviews").fetchall()
print(f"Total pending_reviews rows in DB: {len(pending_rows)}")

accenture_emails = {}
for r in pending_rows:
    try:
        p = json.loads(r[4])
        from_email = p.get('from') or p.get('client_lead_poc') or ''
        subj = p.get('subject') or ''
        req_from = p.get('requirement_from') or ''
        if 'accenture' in req_from.lower() or 'accenture' in subj.lower() or 'accenture' in from_email.lower() or 'anusha' in from_email.lower():
            gid = p.get('graphMessageId') or p.get('internetMessageId') or r[1]
            if gid not in accenture_emails:
                accenture_emails[gid] = {
                    'subject': subj,
                    'from': from_email,
                    'date': p.get('receivedDateTime'),
                    'bodyText': p.get('bodyText'),
                    'bodyHtml': p.get('bodyHtml'),
                    'rows_count': 0,
                    'requirements': []
                }
            accenture_emails[gid]['rows_count'] += 1
            accenture_emails[gid]['requirements'].append(p)
    except Exception as e:
        pass

print(f"Total distinct Accenture emails in pending_reviews: {len(accenture_emails)}")
for gid, info in accenture_emails.items():
    print(f"Email GID: {gid[:30]}... | Date: {info['date']} | Subj: {info['subject']} | From: {info['from']} | Extracted Reqs Count: {info['rows_count']}")

# Also check filtered_log
filtered_rows = cur.execute("SELECT id, graph_id, subject, from_email, reason, stage, created_at FROM filtered_log WHERE subject LIKE '%accenture%' OR from_email LIKE '%anusha%'").fetchall()
print(f"\nTotal Accenture rows in filtered_log: {len(filtered_rows)}")
filtered_emails = {}
for r in filtered_rows:
    gid = r[1]
    if gid not in filtered_emails:
        filtered_emails[gid] = (r[2], r[3], r[6], r[4])

print(f"Total distinct Accenture emails in filtered_log: {len(filtered_emails)}")
for gid, (subj, from_e, dt, reason) in filtered_emails.items():
    print(f"Filtered Email GID: {gid[:30]}... | Date: {dt} | Subj: {subj} | From: {from_e} | Reason: {reason}")

conn.close()
