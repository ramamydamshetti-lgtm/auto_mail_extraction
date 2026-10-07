import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA="

# Check requirement_memory for this gid
rows = conn_proc.execute("SELECT payload_json FROM requirement_memory WHERE source_graph_id = ?", (gid,)).fetchall()
print(f"Total rows extracted from 2026-10-01 09:03 email: {len(rows)}")

req_list = []
for r in rows:
    p = json.loads(r[0])
    cjd = p.get("client_jd_id")
    title = p.get("job_title")
    loc = p.get("location")
    city = loc[0] if isinstance(loc, list) and loc else str(loc or "")
    req_list.append((cjd, title, city, p))

print("\nRequirements in the email:")
for cjd, title, city, p in req_list:
    # Check each store BEFORE processing:
    # 1. requirement_identity: (we know it's 0 rows / not seeded)
    in_identity = False
    
    # 2. client_requirements:
    cr_row = conn_proc.execute("SELECT status, created_at, updated_at FROM client_requirements WHERE client_jd_id = ?", (cjd,)).fetchone()
    
    # 3. metaforge_requirements:
    mf_row = conn_mf.execute("SELECT job_id, created_at, updated_at, field_change_history, payload_json FROM metaforge_requirements WHERE client_jd_id = ?", (cjd,)).fetchone()
    
    # 4. pending_reviews:
    pr_row = conn_proc.execute("SELECT id FROM pending_reviews WHERE client_jd_id = ?", (cjd,)).fetchone()
    
    # 5. duplicates_archive:
    # Check if duplicates_archive table exists
    has_archive = conn_proc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicates_archive'").fetchone() is not None
    
    # Determine if found before processing:
    # Look at created_at vs updated_at or field_change_history
    was_existing = False
    old_job_id = None
    old_created_at = None
    if mf_row:
        fch = json.loads(mf_row[3] or "[]")
        # If created_at is before 2026-10-01 or field_change_history has an entry from 2026-10-01
        old_job_id = mf_row[0]
        old_created_at = mf_row[1]
        if "2026-10-01" not in mf_row[0]: # e.g. 2026/09/22-130
            was_existing = True
    
    print(f"cjd={cjd} | title={title} | city={city} | was_existing={was_existing} | old_job_id={old_job_id} | mf_created={old_created_at}")

conn_proc.close()
conn_mf.close()
