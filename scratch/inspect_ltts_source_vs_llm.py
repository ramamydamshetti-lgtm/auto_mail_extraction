import sqlite3
import json

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%' AND id IN (538, 539, 540, 541)")
rows = c_pm.fetchall()

for pid, gid, jid, cjd, pjson, ca in rows:
    p = json.loads(pjson)
    print("="*70)
    print(f"PENDING REVIEW ID: {pid} | GRAPH ID: {gid}")
    print("="*70)
    print("EXTRACTED PAYLOAD:")
    print(f"  job_title         : {p.get('job_title')}")
    print(f"  location          : {p.get('location')}")
    print(f"  overall_experience: {p.get('overall_experience')}")
    print(f"  mandatory_skills  : {p.get('mandatory_skills')}")
    print(f"  yearly_budget     : {p.get('yearly_budget')}")
    print(f"  monthly_budget    : {p.get('monthly_budget')}")
    print(f"  review_reasons    : {p.get('review_reasons') or p.get('flags')}")
    
    # Check if raw_emails or similar table exists in processed_messages.db to get source text
    c_pm.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('raw_emails', 'emails', 'messages')")
    raw_tbl = c_pm.fetchone()
    if raw_tbl:
        c_pm.execute(f"SELECT subject, body FROM {raw_tbl[0]} WHERE graph_id=?", (gid,))
        erow = c_pm.fetchone()
        if erow:
            print("\nSOURCE EMAIL SUBJECT:", erow[0])
            print("SOURCE EMAIL BODY (first 300 chars):", repr(erow[1][:300]))
    print()

conn_pm.close()
