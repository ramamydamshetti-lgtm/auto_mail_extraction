import sqlite3
import json
import os
from datetime import datetime

DB_PROCESSED = "data/processed_messages.db"
DB_METAFORGE = "data/metaforge_requirements.db"

print("======================================================================")
print("SYNCING VALID EXTRACTED REQUIREMENTS FROM PENDING_REVIEWS TO METAFORGE_REQUIREMENTS.DB")
print("======================================================================")

conn_pm = sqlite3.connect(DB_PROCESSED)
c_pm = conn_pm.cursor()

c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews")
pr_rows = c_pm.fetchall()

print(f"Total Pending Reviews to evaluate: {len(pr_rows)}")

conn_mf = sqlite3.connect(DB_METAFORGE)
c_mf = conn_mf.cursor()

synced_cnt = 0
skipped_header_cnt = 0

for pid, gid, jid, cjd, pjson, ca in pr_rows:
    try:
        p = json.loads(pjson)
    except Exception as e:
        print(f"Error loading JSON for pending review #{pid}: {e}")
        continue
    
    job_title = str(p.get("job_title") or "").strip()
    
    # Filter out known paragraph header sub-items (e.g. "Working in a team led by Lead", "The Senior Civil Structural Engineer will lead")
    low_title = job_title.lower()
    if any(phrase in low_title for phrase in ["working in a team", "the senior civil structural engineer will lead", "development leads and test system engineer"]):
        print(f"Skipping paragraph header sub-item #{pid}: '{job_title}'")
        skipped_header_cnt += 1
        continue
    
    # Ensure client_jd_id and job_id are clean
    final_job_id = jid if jid and jid != "STATUS-UNMATCHED" else f"REQ-{ca[:10]}-{pid:03d}"
    final_client_jd_id = cjd if cjd and cjd != "STATUS-UNMATCHED" else (p.get("client_jd_id") or final_job_id)
    p["job_id"] = final_job_id
    p["client_jd_id"] = final_client_jd_id
    
    # Clean client POC
    client_name = p.get("requirement_from") or "Other"
    if "ITC" in client_name:
        p["client_lead_poc"] = "Divya.Grover@itcinfotech.com"
        p["client_poc"] = "Divya.Grover@itcinfotech.com"
    
    payload_str = json.dumps(p, ensure_ascii=False)
    
    # Insert or replace into metaforge_requirements
    c_mf.execute(
        "INSERT OR REPLACE INTO metaforge_requirements(job_id, payload_json, created_at) VALUES (?, ?, ?)",
        (final_job_id, payload_str, ca)
    )
    
    # Update pipeline_state in processed_messages.db to synced
    c_pm.execute("UPDATE pipeline_state SET state='synced', detail=? WHERE graph_id=?", (f"synced_to_metaforge:{final_job_id}", gid))
    synced_cnt += 1

conn_mf.commit()
conn_pm.commit()

# Delete synced rows from pending_reviews
c_pm.execute("DELETE FROM pending_reviews WHERE id IN (SELECT id FROM pending_reviews)")
conn_pm.commit()

conn_mf.close()
conn_pm.close()

print("\n======================================================================")
print(f"SYNC COMPLETE:")
print(f"  - Successfully Synced to Main DB & UI : {synced_cnt}")
print(f"  - Filtered Sub-header Noise Items     : {skipped_header_cnt}")
print("======================================================================")
