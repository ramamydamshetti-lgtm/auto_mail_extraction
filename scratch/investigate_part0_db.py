import sqlite3
import json
import os

print("=== PART 0: DB CONTAMINATION INVESTIGATION ===")

mf_db = "data/metaforge_requirements.db"
if os.path.exists(mf_db):
    conn = sqlite3.connect(mf_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT job_id, created_at, payload_json FROM metaforge_requirements").fetchall()
    print(f"\n[data/metaforge_requirements.db] Total rows: {len(rows)}")
    
    synthetic_rows = []
    real_rows = []
    
    for r in rows:
        payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        title = payload.get("job_title") or ""
        skills = payload.get("mandatory_skills") or ""
        skills_str = json.dumps(skills)
        job_id = r["job_id"]
        client_jd_id = payload.get("client_jd_id") or payload.get("client_jd_id_override")
        
        is_synth = False
        if "Tech Demand Role #" in title or "Primary Skill Set #" in skills_str or "ACC-2026-SEP-" in str(job_id) or "LTTS-2026-SEP-" in str(job_id):
            is_synth = True
        
        entry = {
            "job_id": job_id,
            "client_jd_id": client_jd_id,
            "created_at": r["created_at"],
            "title": title,
            "client": payload.get("requirement_from")
        }
        
        if is_synth:
            synthetic_rows.append(entry)
        else:
            real_rows.append(entry)
            
    print(f"Synthetic/Test rows found in metaforge_requirements.db: {len(synthetic_rows)}")
    for idx, s in enumerate(synthetic_rows, 1):
        print(f"  {idx}. [SYNTHETIC] {s['job_id']} | client_jd_id: {s['client_jd_id']} | client: {s['client']} | title: {s['title'][:50]}")
        
    print(f"\nReal rows found in metaforge_requirements.db: {len(real_rows)}")
    for idx, r_row in enumerate(real_rows, 1):
        print(f"  {idx}. [REAL] {r_row['job_id']} | client_jd_id: {r_row['client_jd_id']} | client: {r_row['client']} | title: {r_row['title'][:50]}")
        
    conn.close()

# Check pending_reviews in data/processed_messages.db
pm_db = "data/processed_messages.db"
if os.path.exists(pm_db):
    conn = sqlite3.connect(pm_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews").fetchall()
    print(f"\n[data/processed_messages.db: pending_reviews] Total rows: {len(rows)}")
    for idx, r in enumerate(rows, 1):
        p = json.loads(r["payload_json"]) if r["payload_json"] else {}
        print(f"  {idx}. Pending ID: {r['job_id']} | client_jd_id: {r['client_jd_id']} | title: {p.get('job_title')[:40]} | created: {r['created_at']}")
    conn.close()
