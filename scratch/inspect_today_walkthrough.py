import sqlite3
import json

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()

print("=== SAMPLE EMAILS PROCESSED TODAY (2026-09-29) ===")

# 1. Synced Active Requirement
print("\n--- SAMPLE 1: Synced Active Requirement (Accenture) ---")
c_mr.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE created_at LIKE '2026-09-29%' LIMIT 1")
row = c_mr.fetchone()
if row:
    job_id, pjson, ca = row
    p = json.loads(pjson)
    print(f"Job ID: {job_id}")
    print(f"Created At: {ca}")
    print("Stored Requirement Fields:")
    for k, v in p.items():
        print(f"  {k}: {v}")

# 2. Pending Reviews Requirements (LTTS & ITC Infotech)
print("\n--- SAMPLE 2 & 3: Pending Review Requirements (LTTS & ITC Infotech) ---")
c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%' LIMIT 4")
pr_rows = c_pm.fetchall()
for r in pr_rows:
    pid, gid, jid, cjd, pjson, ca = r
    p = json.loads(pjson)
    print(f"\n[Pending Review ID: {pid} | Job ID: {jid}]")
    print(f"  Client: {p.get('requirement_from')} | Title: {p.get('job_title')}")
    print(f"  Location: {p.get('location')} | Exp: {p.get('overall_experience')} | Skills: {p.get('mandatory_skills')}")
    print(f"  Yearly Budget: '{p.get('yearly_budget')}' | Monthly Budget: '{p.get('monthly_budget')}'")

# 3. Filtered / Skipped Emails (sender_not_allowlisted & operational)
print("\n--- SAMPLE 4-7: Filtered / Skipped Emails ---")
c_pm.execute("SELECT id, graph_id, subject, from_email, reason, stage, created_at FROM filtered_log WHERE created_at LIKE '2026-09-29%' LIMIT 5")
fl_rows = c_pm.fetchall()
for r in fl_rows:
    fid, gid, subj, from_e, reason, stage, ca = r
    print(f"[Filtered Log ID: {fid}]")
    print(f"  Subject: {subj}")
    print(f"  From: {from_e}")
    print(f"  Stage: {stage} | Reason: {reason}")
    print(f"  Created At: {ca}\n")

c_pm.execute("SELECT graph_id, state, detail, updated_at FROM pipeline_state WHERE state='skipped' AND updated_at LIKE '2026-09-29%' LIMIT 5")
ps_rows = c_pm.fetchall()
print("Pipeline state skipped samples:")
for r in ps_rows:
    print(f"  Graph ID: {r[0][:30]}... | Detail: {r[2]}")

conn_pm.close()
conn_mr.close()
