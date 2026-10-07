import sys, os
sys.path.insert(0, os.path.abspath('.'))
import sqlite3
import json
from boilerplate_learner import clean_structure_and_extract_boilerplate, validate_skills
from strict_validator import _is_candidate_table_noise

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
row = c.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/10/05-011'").fetchone()
payload = json.loads(row[0])
body = payload.get('bodyText') or ''
conn.close()

cleaned, removed = clean_structure_and_extract_boilerplate(body, client='LTTS')
print('Removed lines count:', len(removed))
for r in removed:
    print('  REMOVED:', r)

skills_011 = [
    "Strong fundamentals in power electronics and analog hardware design",
    "Hands-on experience with LTspice, MATLAB/Simulink, PSIM/PLECS, SIMPLIS",
    "Experience with MOSFET, SiC/GaN, gate driver, sensing, and EMI/EMC considerations",
    "Understanding of PCB layout practices for high-voltage and high-power applications",
    "TI C2000 and digital power control",
]

print("\n--- Current validate_skills without removed_lines ---")
print(validate_skills(skills_011, client='LTTS'))

print("\n--- Current validate_skills WITH removed_lines ---")
print(validate_skills(skills_011, client='LTTS', removed_lines=removed))
