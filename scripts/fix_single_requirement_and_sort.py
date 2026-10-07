import sqlite3
import json

db_path = 'data/metaforge_requirements.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Remove 2026/10/05-013 so that October 05 has only ONE requirement (2026/10/05-012)
cur.execute("DELETE FROM metaforge_requirements WHERE job_id = '2026/10/05-013'")
print(f"Deleted 2026/10/05-013: {cur.rowcount} row(s) deleted.")

# Update 2026/10/05-012 to ensure it represents the consolidated single requirement
cur.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/10/05-012'")
row = cur.fetchone()
if row:
    p12 = json.loads(row[0])
    p12['role_title'] = 'Project Engineer'
    p12['job_title'] = 'Project Engineer'
    cur.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = '2026/10/05-012'", (json.dumps(p12),))
    print("Updated 2026/10/05-012 as single consolidated requirement.")

# 2. Update 2026/10/07-009 Design Engineer to exactly match the screenshot
cur.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/10/07-009'")
row_009 = cur.fetchone()
if row_009:
    p009 = json.loads(row_009[0])
    p009['job_title'] = 'Design Engineer'
    p009['role_title'] = 'Design Engineer'
    p009['overall_experience'] = '4-5 Years'
    p009['experience'] = '4-5 Years'
    p009['overall_experience_min'] = 4
    p009['overall_experience_max'] = 5
    p009['number_of_positions'] = 2
    p009['qualification'] = 'BE/BTech'
    p009['educational_qualifications'] = 'Bachelor in BE/ BTech in Electronics/Electrical/Biomedical Engineering'
    p009['domain_specification'] = 'Electrical and Electronics'
    p009['mandatory_skills'] = ['PCB Hardware']
    p009['skills'] = [
        'PCB Hardware',
        'Medical Device Development or Life Cycle Management Activities',
        'IEC and ISO Standard relevant to medical device',
        'Engineering change management process',
        'Altium / Mentor Xpedition / Similar'
    ]
    p009['monthly_budget'] = 100000
    p009['budget'] = '100000'
    p009['budget_text'] = '100000'
    p009['budget_currency'] = 'INR'
    p009['rate_card'] = 100000
    p009['notice_period'] = 'ONLY IMMEDIATE JOINERS REQUIRED'
    p009['work_location'] = 'PUNE'
    p009['location'] = 'Pune'
    p009['requirement_from'] = 'LTTS'
    p009['client_key'] = 'ltts'
    p009['job_status'] = 'open'
    p009['requirement_status'] = 'open'

    cur.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = '2026/10/07-009'", (json.dumps(p009),))
    print("Updated 2026/10/07-009 Design Engineer with all exact fields.")

conn.commit()
conn.close()

# Also clean up from processed_messages.db if present
proc_db = 'data/processed_messages.db'
conn_proc = sqlite3.connect(proc_db)
cur_proc = conn_proc.cursor()
cur_proc.execute("DELETE FROM requirement_identity WHERE original_record_ref = '2026/10/05-013' OR profile_json LIKE '%2026/10/05-013%'")
print(f"Removed 2026/10/05-013 from processed_messages.db: {cur_proc.rowcount} row(s)")
conn_proc.commit()
conn_proc.close()


print("Database update complete!")
