import sqlite3
import json
from pathlib import Path

DATA_DIR = Path("g:/Auto_email_extraction (3)-new/Auto_email_extraction/data")
proc_db = DATA_DIR / "processed_messages.db"
mf_db = DATA_DIR / "metaforge_requirements.db"

conn_proc = sqlite3.connect(f"file:{proc_db}?mode=ro", uri=True)
conn_mf = sqlite3.connect(f"file:{mf_db}?mode=ro", uri=True)

# The 34 client IDs
client_ids = [
    '198381-1', '198377-1', '188662-1', '200134-1', '200968-1', '203502-1',
    '203421-1', '203190-1', '203484-1', '204307-1', '203146-1', '204241-1', '204237-1',
    '204617-1', '205118-1', '206291-1', '206678-1', '186544-1', '207725-1', '187291-1',
    '187643-1', '187686-1', '187653-1', '187663-1', '187654-1', '187657-1', '187664-1',
    '188848-1', '187655-1', '187651-1', '187638-1', '187648-1', '188603-1', '209160-1'
]

print(f"Investigating {len(client_ids)} overwritten rows...")

diff_reports = []

for cjd in client_ids:
    # 1. Current state in metaforge_requirements
    mf_row = conn_mf.execute("SELECT job_id, payload_json, created_at, updated_at, field_change_history FROM metaforge_requirements WHERE client_jd_id = ?", (cjd,)).fetchone()
    if not mf_row:
        continue
    
    cur_job_id, cur_p_str, cur_created, cur_updated, cur_fch_str = mf_row
    cur_payload = json.loads(cur_p_str)
    cur_fch = json.loads(cur_fch_str or "[]")
    
    # 2. Check field_change_history for the 2026-10-01 change
    today_change = None
    for h in cur_fch:
        if "2026-10-01" in h.get("changed_at", ""):
            today_change = h
            break
            
    # 3. Check requirement_memory for previous records with this cjd from older emails
    mem_rows = conn_proc.execute("SELECT source_graph_id, payload_json, created_at FROM requirement_memory WHERE payload_json LIKE ? ORDER BY created_at ASC", (f"%{cjd}%",)).fetchall()
    
    older_mem_payload = None
    for gid, p_str, cat in mem_rows:
        if "2026-10-01" not in cat: # Prior to today
            try:
                p = json.loads(p_str)
                if p.get("client_jd_id") == cjd:
                    older_mem_payload = (gid, p, cat)
                    break
            except Exception:
                pass
                
    diff_reports.append({
        "client_jd_id": cjd,
        "job_id": cur_job_id,
        "created_at": cur_created,
        "updated_at": cur_updated,
        "today_changes": today_change.get("changes") if today_change else {},
        "current_demand_received_date": cur_payload.get("demand_received_date"),
        "current_receivedDateTime": cur_payload.get("receivedDateTime"),
        "current_email_received_iso": cur_payload.get("email_received_iso"),
        "current_prov": cur_payload.get("_provenance"),
        "older_mem_found": bool(older_mem_payload),
        "older_mem_date": older_mem_payload[1].get("demand_received_date") if older_mem_payload else None,
        "older_mem_received": older_mem_payload[1].get("receivedDateTime") if older_mem_payload else None,
        "older_mem_prov": older_mem_payload[1].get("_provenance") if older_mem_payload else None,
    })

print(f"Analyzed {len(diff_reports)} records.")
with open("scratch/inspect_34_diffs.json", "w", encoding="utf-8") as f:
    json.dump(diff_reports, f, indent=2)

conn_proc.close()
conn_mf.close()
