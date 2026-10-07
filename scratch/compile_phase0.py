import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA="
rows = conn_proc.execute("SELECT payload_json FROM requirement_memory WHERE source_graph_id = ?", (gid,)).fetchall()

print(f"Total rows: {len(rows)}")

client_ids = [
    '198381-1', '198377-1', '188662-1', '200134-1', '200964-1', '200968-1', '203502-1',
    '203421-1', '203190-1', '203484-1', '204307-1', '203146-1', '204241-1', '204237-1',
    '204617-1', '205118-1', '206291-1', '206678-1', '186544-1', '207725-1', '187291-1',
    '187643-1', '187686-1', '187653-1', '187663-1', '187654-1', '187657-1', '187664-1',
    '188848-1', '187655-1', '187651-1', '187638-1', '187648-1', '188603-1', '209160-1'
]

results = []

for cjd in client_ids:
    # Find payload in requirement_memory
    p_mem = None
    for r in rows:
        p = json.loads(r[0])
        if p.get("client_jd_id") == cjd:
            p_mem = p
            break
    
    title = p_mem.get("job_title") if p_mem else ""
    loc = p_mem.get("location") if p_mem else ""
    city = loc[0] if isinstance(loc, list) and loc else str(loc or "")
    
    # Store presence before processing:
    # 1. requirement_identity:
    # Was it in requirement_identity? No, requirement_identity was empty / didn't exist
    in_id = "NO"
    
    # 2. client_requirements:
    cr_row = conn_proc.execute("SELECT status, created_at, updated_at FROM client_requirements WHERE client_jd_id = ?", (cjd,)).fetchone()
    in_cr = "YES" if (cr_row and cr_row[1] < "2026-10-01T04:13:00") else "NO"
    
    # 3. metaforge_requirements:
    mf_row = conn_mf.execute("SELECT job_id, created_at, updated_at, field_change_history, payload_json FROM metaforge_requirements WHERE client_jd_id = ?", (cjd,)).fetchone()
    in_mf = "NO"
    old_job_id = None
    orig_created_at = None
    orig_demand_date = None
    if mf_row:
        old_job_id = mf_row[0]
        orig_created_at = mf_row[1]
        fch = json.loads(mf_row[3] or "[]")
        # Check if row existed before 2026-10-01
        if "2026-10-01" not in mf_row[0]: # Job ID from September
            in_mf = "YES"
            # Get original demand_received_date if in fch
            for h in fch:
                if "demand_received_date" in h.get("changes", {}):
                    orig_demand_date = h["changes"]["demand_received_date"].get("old")
        elif cjd != "200964-1":
            in_mf = "YES"
        else:
            in_mf = "NO"
            
    # 4. pending_reviews:
    pr_row = conn_proc.execute("SELECT id FROM pending_reviews WHERE client_jd_id = ?", (cjd,)).fetchone()
    in_pr = "YES" if pr_row else "NO"
    
    # 5. duplicates_archive:
    in_da = "NO"
    
    # Decision taken:
    decision = "new" if cjd == "200964-1" else "updated" # Because _sqlite_upsert updated it
    code_path = "table extractor -> main.py pipeline -> metaforge_api._sqlite_upsert"
    
    # Columns changed:
    if cjd == "200964-1":
        cols_changed = "All (NEW INSERT: job_id=2026/10/01-005, created_at=2026-10-01, demand_received_date=2026-10-01)"
    else:
        # What changed in metaforge_requirements:
        fch_changes = []
        if mf_row:
            fch = json.loads(mf_row[3] or "[]")
            for h in fch:
                if h.get("source_email_id") == gid:
                    fch_changes = list(h.get("changes", {}).keys())
        cols_changed = f"updated_at, payload_json.demand_received_date (old={orig_demand_date or 'pre-10/01'}, new=2026-10-01)"
        if fch_changes:
            cols_changed += f", payload fields: {fch_changes}"
            
    results.append({
        "cjd": cjd,
        "title": title,
        "city": city,
        "in_id": in_id,
        "in_cr": in_cr,
        "in_mf": in_mf,
        "in_pr": in_pr,
        "in_da": in_da,
        "decision": decision,
        "code_path": code_path,
        "cols_changed": cols_changed,
        "old_job_id": old_job_id,
        "orig_created_at": orig_created_at,
    })

print(f"Diagnosed {len(results)} rows.")
with open("scratch/phase0_rows.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

conn_proc.close()
conn_mf.close()
