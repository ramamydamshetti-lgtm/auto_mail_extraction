import sqlite3
import json
import re
from collections import Counter

print("=" * 60)
print("AUDIT: data/metaforge_requirements.db")
print("=" * 60)

conn_mf = sqlite3.connect("data/metaforge_requirements.db")
c_mf = conn_mf.cursor()

tables = [t[0] for t in c_mf.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables in metaforge_requirements.db: {tables}")

for tbl in tables:
    cnt = c_mf.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    print(f"Table '{tbl}': {cnt} rows")

rows = c_mf.execute("SELECT job_id, client_jd_id, payload_json, created_at, updated_at FROM metaforge_requirements").fetchall()
print(f"\nTotal rows in metaforge_requirements: {len(rows)}")

synthetic_acc_ltts = []
suspicious_placeholder_text = []
missing_provenance = []
verified_real = []

placeholder_patterns = [
    r"Tech Demand Role #",
    r"Primary Skill Set #",
    r"Role #\d+",
    r"Skill Set #\d+",
    r"ACC-2026-SEP-",
    r"LTTS-2026-SEP-",
    r"Placeholder",
    r"\bTest\b",
    r"\bSample\b",
    r"\bDemo\b"
]

for r in rows:
    job_id, client_jd_id, payload_json, created_at, updated_at = r
    p = json.loads(payload_json) if payload_json else {}
    
    # Check for ~190 synthetic rows
    raw_str = f"{job_id} {client_jd_id} {payload_json}"
    if "ACC-2026-SEP-" in raw_str or "LTTS-2026-SEP-" in raw_str or "Tech Demand Role #" in raw_str or "Primary Skill Set #" in raw_str:
        synthetic_acc_ltts.append({
            "job_id": job_id,
            "client_jd_id": client_jd_id,
            "created_at": created_at
        })
        continue

    # Check for placeholder patterns in job title, skills, client
    is_placeholder = False
    for pat in placeholder_patterns:
        title_str = str(p.get("job_title") or "")
        skills_str = str(p.get("mandatory_skills") or "")
        if re.search(pat, title_str, re.IGNORECASE) or re.search(pat, skills_str, re.IGNORECASE):
            suspicious_placeholder_text.append({
                "job_id": job_id,
                "client_jd_id": client_jd_id,
                "title": p.get("job_title"),
                "skills": p.get("mandatory_skills")
            })
            is_placeholder = True
            break
    if is_placeholder:
        continue

    # Check provenance to find real source email
    prov = p.get("_provenance", {}) if isinstance(p.get("_provenance"), dict) else {}
    email_id = prov.get("email_id") or prov.get("graph_id") or p.get("email_id") or p.get("graph_id") or p.get("message_id")
    sender = p.get("from") or p.get("sender") or prov.get("sender") or prov.get("from") or p.get("client_poc") or p.get("client_lead_poc")
    received_time = prov.get("received_date_time") or p.get("receivedDateTime") or p.get("email_received_iso") or p.get("received_at")
    
    if not email_id or not sender or not received_time:
        missing_provenance.append({
            "job_id": job_id,
            "client_jd_id": client_jd_id,
            "email_id": email_id,
            "sender": sender,
            "received_time": received_time
        })
    else:
        verified_real.append({
            "job_id": job_id,
            "client_jd_id": client_jd_id,
            "sender": sender,
            "email_id": email_id,
            "received_time": received_time,
            "subject": p.get("subject") or prov.get("subject"),
            "role": p.get("job_title")
        })

print(f"\n--- AUDIT RESULTS FOR metaforge_requirements.db ---")
print(f"1. Synthetic ACC/LTTS rows (ACC-2026-SEP-*, LTTS-2026-SEP-*, 'Tech Demand Role #'): {len(synthetic_acc_ltts)}")
print(f"2. Other suspicious placeholder rows ('Test', 'Sample', 'Placeholder', 'Role #'): {len(suspicious_placeholder_text)}")
if suspicious_placeholder_text:
    for sp in suspicious_placeholder_text:
        print(f"   - {sp}")
print(f"3. Rows missing provenance (email_id / sender / received_time): {len(missing_provenance)}")
if missing_provenance:
    for mp in missing_provenance:
        print(f"   - {mp}")
print(f"4. Traceable to real source emails: {len(verified_real)}")

print("\n" + "=" * 60)
print("AUDIT: data/processed_messages.db")
print("=" * 60)
conn_pm = sqlite3.connect("data/processed_messages.db")
c_pm = conn_pm.cursor()
tables_pm = [t[0] for t in c_pm.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for tbl in tables_pm:
    cnt = c_pm.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    print(f"Table '{tbl}': {cnt} rows")

# Check requirement_memory
rows_mem = c_pm.execute("SELECT id, requirement_from, job_title_norm, payload_json, source_graph_id FROM requirement_memory").fetchall()
syn_mem = 0
for rm in rows_mem:
    raw = f"{rm[0]} {rm[1]} {rm[2]} {rm[3]}"
    if "ACC-2026-SEP-" in raw or "LTTS-2026-SEP-" in raw or "Tech Demand Role #" in raw:
        syn_mem += 1
print(f"requirement_memory rows matching synthetic ACC/LTTS: {syn_mem} / {len(rows_mem)}")

# Check pending_reviews
rows_pr = c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json FROM pending_reviews").fetchall()
print(f"pending_reviews rows: {len(rows_pr)}")
for pr in rows_pr:
    print(f"  ID: {pr[0]} | Graph ID: {pr[1]} | Job ID: {pr[2]} | Client JD: {pr[3]}")
