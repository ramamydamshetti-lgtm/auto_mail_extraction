import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()

print("=== INSPECTING PENDING_REVIEWS ===")
rows = cur.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%' LIMIT 10").fetchall()
for r in rows:
    p = json.loads(r[4])
    print(f"ID={r[0]} | job_id={r[2]} | client_jd_id={r[3]}")
    print("Keys in payload:", list(p.keys()))
    print("Job title:", p.get('job_title'))
    print("Status:", p.get('status'))
    print("Provenance / Source:", p.get('_provenance') or p.get('source'))
    print("Raw text / summary:", str(p.get('summary') or p.get('jd_text'))[:200])
    print("-" * 50)

print("\n=== INSPECTING FILTERED_LOG ===")
rows = cur.execute("SELECT id, graph_id, subject, from_email, reason, stage, created_at FROM filtered_log WHERE subject LIKE '%accenture%' LIMIT 10").fetchall()
for r in rows:
    print(r)

conn.close()
