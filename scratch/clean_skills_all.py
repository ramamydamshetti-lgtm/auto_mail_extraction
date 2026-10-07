import sqlite3
import json
import re

def clean_skills_list(skills):
    if not skills or not isinstance(skills, list):
        return skills
    cleaned = []
    for s in skills:
        s_str = str(s).strip()
        if not s_str or len(s_str) < 2:
            continue
        # Check against recruiter, address, and contact artifacts
        if re.search(r'(?i)(?:technologies|pvt\s*ltd|iso\s*27001|bhuvanappa|layout|crystal\s+plaza|hosur|road|bengaluru|bangalore|mob:|tel:|http|talent\s+acquisition|lead\s*-|idexcel|deloitte|metaforge|accenture|recruiter|hr\s+team|rahul\s+saha|vaishnavi|lead-talent|redacted|@[a-z0-9\.\-_]+|\b\d{10}\b)', s_str):
            continue
        cleaned.append(s_str)
    return cleaned

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()

for r in rows:
    p = json.loads(r['payload_json'])
    old_sk = p.get('skills')
    if old_sk and isinstance(old_sk, list):
        new_sk = clean_skills_list(old_sk)
        if new_sk != old_sk:
            p['skills'] = new_sk
            conn.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?",
                         (json.dumps(p, ensure_ascii=False), r['job_id']))

conn.commit()

# Check RQ056293 skills now
r044 = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE client_jd_id = 'RQ056293'").fetchone()
p044 = json.loads(r044['payload_json'])
print("Cleaned skills for RQ056293:", p044.get('skills'))
print("Mandatory skills for RQ056293:", p044.get('mandatory_skills'))

conn.close()
