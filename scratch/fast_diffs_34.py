import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

client_ids = [
    '198381-1', '198377-1', '188662-1', '200134-1', '200968-1', '203502-1',
    '203421-1', '203190-1', '203484-1', '204307-1', '203146-1', '204241-1', '204237-1',
    '204617-1', '205118-1', '206291-1', '206678-1', '186544-1', '207725-1', '187291-1',
    '187643-1', '187686-1', '187653-1', '187663-1', '187654-1', '187657-1', '187664-1',
    '188848-1', '187655-1', '187651-1', '187638-1', '187648-1', '188603-1', '209160-1'
]

results = []
for cjd in client_ids:
    row = conn_mf.execute(
        "SELECT job_id, client_jd_id, created_at, updated_at, field_change_history, payload_json FROM metaforge_requirements WHERE client_jd_id = ?",
        (cjd,)
    ).fetchone()
    if not row:
        continue
    job_id, cid, created_at, updated_at, fch_str, p_str = row
    p = json.loads(p_str)
    fch = json.loads(fch_str or "[]")
    
    # Find change from 2026-10-01
    c1001 = None
    for h in fch:
        if "2026-10-01" in h.get("changed_at", ""):
            c1001 = h
            break
            
    changes = c1001.get("changes", {}) if c1001 else {}
    
    # Derivation of original date from job_id (e.g. 2026/09/22-130 -> 2026-09-22)
    job_date = None
    if "/" in job_id and "-" in job_id:
        # e.g. 2026/09/22-130
        part = job_id.split("-")[0] # 2026/09/22
        job_date = part.replace("/", "-")
        
    results.append({
        "client_jd_id": cjd,
        "job_id": job_id,
        "created_at": created_at,
        "updated_at": updated_at,
        "job_date": job_date,
        "current_demand_received_date": p.get("demand_received_date"),
        "current_receivedDateTime": p.get("receivedDateTime"),
        "current_email_received_iso": p.get("email_received_iso"),
        "current_prov": p.get("_provenance"),
        "changes_recorded": changes,
        "old_demand_received_date": changes.get("demand_received_date", {}).get("old"),
    })

print(f"Collected diffs for {len(results)} requirements.")
with open("scratch/diffs_34.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

conn_mf.close()
