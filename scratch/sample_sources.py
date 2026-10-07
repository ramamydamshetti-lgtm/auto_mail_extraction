import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements LIMIT 5")
rows = c.fetchall()

print("=== INSPECTING FIELD SOURCES FOR 5 SAMPLE REQUIREMENTS ===")
for job_id, cjd, p_json in rows:
    p = json.loads(p_json)
    print(f"\n--- Job ID: {job_id} | Client JD ID: {cjd} ---")
    print(f"Title: {p.get('job_title')}")
    print(f"Client: {p.get('requirement_from')} | POC: {p.get('client_poc')}")
    print(f"Location: {p.get('location')}")
    print(f"Skills: {p.get('skills')}")
    print(f"Mandatory: {p.get('mandatory_skills')}")
    print(f"Exp: {p.get('overall_experience')} (min={p.get('overall_experience_min')}, max={p.get('overall_experience_max')})")
    print(f"Budget: {p.get('budget')} / {p.get('monthly_budget')} / {p.get('yearly_budget')}")
    print(f"Positions: {p.get('number_of_positions')}")
    print(f"Notice: {p.get('notice_period')}")
    print(f"Work Mode: {p.get('work_mode')}")
    print(f"AutofillMeta: {p.get('autofillMeta')}")
    prov = p.get('_provenance')
    if prov:
        print(f"Provenance: {prov}")
