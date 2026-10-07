import sqlite3
import json
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from ui.app import load_config
from ui.db import fetch_all_records

conn_proc = sqlite3.connect("data/processed_messages.db")
conn_mf = sqlite3.connect("data/metaforge_requirements.db")
cfg = load_config()
ui_records = fetch_all_records(cfg)

# Find UI records by job_id or client_jd_id
ui_by_id = {}
for r in ui_records:
    p = r.get("payload") or {}
    jid = r.get("fmt_id") or r.get("raw_req_id") or p.get("job_id")
    cjd = r.get("client_jd_id") or p.get("client_jd_id")
    if jid: ui_by_id[jid] = r
    if cjd: ui_by_id[cjd] = r

# Candidate 5 requirements to trace:
# 1. Pega Marketing (203529-1 / 2026/09/08-005) - Accenture
# 2. Lead Power System Engineer (2026/09/07-023) - LTTS
# 3. Data Scientist (2026/09/08-001) - KPMG / Poonam Pal
# 4. Sr Data Scientist (2026/09/23-006 / PCIIL_[REDACTED_PHONE]_1) - ITC Infotech
# 5. SAP Plant Maintenance (PM) (202661-1 / 2026/09/25-044) - Accenture

targets = [
    {"name": "Pega Marketing (Accenture)", "cjd": "203529-1", "jid": "2026/09/08-005"},
    {"name": "Lead Power System Engineer (LTTS)", "cjd": None, "jid": "2026/09/07-023"},
    {"name": "Data Scientist (KPMG)", "cjd": None, "jid": "2026/09/08-001"},
    {"name": "Sr Data Scientist (ITC Infotech)", "cjd": "PCIIL_[REDACTED_PHONE]_1", "jid": "2026/09/23-006"},
    {"name": "ServiceNow ITAM Administrator (Accenture)", "cjd": "204237-1", "jid": "2026/09/30-007"},
]

results = []

for t in targets:
    info = {"target": t, "email": {}, "db": {}, "ui": {}}
    
    # 1. UI Record
    ui_r = ui_by_id.get(t["jid"]) or (ui_by_id.get(t["cjd"]) if t["cjd"] else None)
    if ui_r:
        p = ui_r.get("payload") or {}
        info["ui"] = {
            "job_id": ui_r.get("fmt_id") or p.get("job_id"),
            "client_jd_id": ui_r.get("client_jd_id") or p.get("client_jd_id"),
            "client": p.get("requirement_from") or ui_r.get("client"),
            "job_title": p.get("job_title") or ui_r.get("job_title"),
            "location": p.get("location"),
            "work_mode": p.get("work_mode"),
            "experience": p.get("overall_experience") or p.get("experience"),
            "experience_level": p.get("experience_level"),
            "mandatory_skills": p.get("mandatory_skills"),
            "skills": p.get("skills"),
            "notice_period": p.get("notice_period"),
            "budget_yearly": p.get("yearly_budget"),
            "budget_monthly": p.get("monthly_budget"),
            "budget_text": p.get("budget_text"),
            "positions": p.get("number_of_positions"),
            "status": ui_r.get("job_status") or p.get("job_status"),
            "history": ui_r.get("field_change_history") or p.get("field_change_history"),
            "provenance": p.get("_provenance"),
            "graph_message_id": p.get("graphMessageId") or (p.get("_provenance") or {}).get("graph_message_id")
        }
    
    # 2. DB Record (client_requirements or metaforge_requirements or requirement_memory)
    gid = (info["ui"] or {}).get("graph_message_id")
    row_mf = None
    if t["jid"]:
        row_mf = conn_mf.execute("SELECT payload_json, created_at, updated_at FROM metaforge_requirements WHERE job_id=?", (t["jid"],)).fetchone()
    
    row_mem = None
    if gid:
        row_mem = conn_proc.execute("SELECT payload_json FROM requirement_memory WHERE source_graph_id=?", (gid,)).fetchone()
    elif t["cjd"]:
        row_mem = conn_proc.execute("SELECT payload_json FROM requirement_memory WHERE payload_json LIKE ?", (f'%{t["cjd"]}%',)).fetchone()
    
    db_p = None
    if row_mf:
        db_p = json.loads(row_mf[0])
    elif row_mem:
        db_p = json.loads(row_mem[0])
        
    if db_p:
        info["db"] = {
            "job_id": db_p.get("job_id"),
            "client_jd_id": db_p.get("client_jd_id"),
            "job_title": db_p.get("job_title"),
            "location": db_p.get("location"),
            "work_mode": db_p.get("work_mode"),
            "experience": db_p.get("overall_experience") or db_p.get("experience"),
            "mandatory_skills": db_p.get("mandatory_skills"),
            "skills": db_p.get("skills"),
            "notice_period": db_p.get("notice_period"),
            "budget_yearly": db_p.get("yearly_budget"),
            "budget_monthly": db_p.get("monthly_budget"),
            "positions": db_p.get("number_of_positions"),
            "status": db_p.get("job_status"),
        }
        
    # 3. Email Body Text
    body_text = None
    if row_mem:
        p_mem = json.loads(row_mem[0])
        body_text = p_mem.get("bodyText")
    elif db_p and db_p.get("bodyText"):
        body_text = db_p.get("bodyText")
        
    if body_text:
        info["email"] = {
            "body_length": len(body_text),
            "body_snippet": body_text[:600],
            "full_body": body_text
        }
        
    results.append(info)

print(json.dumps([{
    "target": r["target"],
    "email_len": r["email"].get("body_length"),
    "ui": r["ui"],
    "db": r["db"]
} for r in results], indent=2, default=str))
