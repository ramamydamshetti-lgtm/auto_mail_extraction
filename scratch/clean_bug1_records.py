import sqlite3
import json

# Clean metaforge_requirements.db
conn_mf = sqlite3.connect('data/metaforge_requirements.db')
c_mf = conn_mf.cursor()

# 2026/09/08-005: Pega Marketing
row = c_mf.execute('SELECT payload_json FROM metaforge_requirements WHERE job_id = ?', ('2026/09/08-005',)).fetchone()
if row:
    p = json.loads(row[0])
    p['mandatory_skills'] = ['Candidates must mandatorily possess CSA, CSSA, and CDH certifications']
    p['skills'] = ['Pega CDH', 'Pega Decisioning']
    c_mf.execute('UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?', (json.dumps(p, ensure_ascii=False), '2026/09/08-005'))

# 2026/09/30-007: ServiceNow ITAM Administrator
row = c_mf.execute('SELECT payload_json FROM metaforge_requirements WHERE job_id = ?', ('2026/09/30-007',)).fetchone()
if row:
    p = json.loads(row[0])
    p['mandatory_skills'] = ['ServiceNow ITAM Administrator']
    p['skills'] = ['ServiceNow ITAM', 'IT Asset Management']
    c_mf.execute('UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?', (json.dumps(p, ensure_ascii=False), '2026/09/30-007'))

conn_mf.commit()
conn_mf.close()

# Also clean requirement_memory and client_requirements in processed_messages.db
conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

for cid in ['203529-1', '203528-1', '203514-1']:
    r = c_pm.execute('SELECT payload_json FROM client_requirements WHERE client_jd_id = ?', (cid,)).fetchone()
    if r:
        p = json.loads(r[0])
        p['mandatory_skills'] = ['Candidates must mandatorily possess CSA, CSSA, and CDH certifications']
        p['skills'] = ['Pega CDH', 'Pega Decisioning']
        c_pm.execute('UPDATE client_requirements SET payload_json = ? WHERE client_jd_id = ?', (json.dumps(p, ensure_ascii=False), cid))

# Clean requirement_memory for pega marketing
rows_pm = c_pm.execute("SELECT id, payload_json FROM requirement_memory WHERE job_title_norm = 'pega marketing'").fetchall()
for rid, p_str in rows_pm:
    p = json.loads(p_str)
    p['mandatory_skills'] = ['Candidates must mandatorily possess CSA, CSSA, and CDH certifications']
    p['skills'] = ['Pega CDH', 'Pega Decisioning']
    c_pm.execute("UPDATE requirement_memory SET payload_json = ? WHERE id = ?", (json.dumps(p, ensure_ascii=False), rid))

# Clean requirement_memory for servicenow
rows_pm = c_pm.execute("SELECT id, payload_json FROM requirement_memory WHERE job_title_norm LIKE '%servicenow%'").fetchall()
for rid, p_str in rows_pm:
    p = json.loads(p_str)
    all_s = str(p.get('skills') or '') + str(p.get('mandatory_skills') or '')
    if 'sap' in all_s.lower():
        p['mandatory_skills'] = ['ServiceNow ITAM Administrator']
        p['skills'] = ['ServiceNow ITAM', 'IT Asset Management']
        c_pm.execute("UPDATE requirement_memory SET payload_json = ? WHERE id = ?", (json.dumps(p, ensure_ascii=False), rid))

conn_pm.commit()
conn_pm.close()
print("Cleaned Bug 1 records successfully.")
