import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE payload_json LIKE '%autofillMeta%' LIMIT 5")
rows = c.fetchall()

print("=== INSPECTING REQUIREMENTS WITH AUTOFILL ===")
for job_id, cjd, p_json in rows:
    p = json.loads(p_json)
    print(f"\n--- Job ID: {job_id} | Client JD ID: {cjd} ---")
    print(f"Title: {p.get('job_title')}")
    print(f"Client: {p.get('requirement_from')}")
    print(f"Work Mode: {p.get('work_mode')}")
    print(f"Notice: {p.get('notice_period')}")
    print(f"Priority: {p.get('priority')}")
    print(f"Employment Type: {p.get('employment_type')}")
    print(f"AutofillMeta: {p.get('autofillMeta')}")
