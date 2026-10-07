import sqlite3
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Auto_email_extraction'))

from config import Settings, is_strict_field_mapping
from requirement_parser import parse_requirements_from_email
from field_mapper import map_to_metaforge
from strict_validator import validate_requirement_before_save
from ui.db import get_requirement

UI_CONFIG = {
    "db_paths": ["Auto_email_extraction/data/metaforge_requirements.db"],
    "processed_db": "Auto_email_extraction/data/processed_messages.db"
}

con = sqlite3.connect('Auto_email_extraction/data/metaforge_requirements.db')
cur = con.cursor()

candidate_ids = [
    '2026/10/05-011',
    '2026/10/05-010',
    '2026/10/05-009',
    '2026/09/30-006',
    '2026/09/30-007',
    '2026/09/08-004',
    '2026/09/08-005',
    '2026/09/17-004',
    '2026/09/07-013',
    '2026/09/11-159',
    '2026/09/29-024',
    '2026/09/21-002',
    '2026/09/11-001',
    '2026/09/07-023'
]

print("Checking presence of candidates in metaforge_requirements:")
found = []
for cid in candidate_ids:
    row = cur.execute('SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ?', (cid, cid)).fetchone()
    if row:
        p = json.loads(row[2])
        found.append((row[0], row[1], p.get('job_title'), p.get('requirement_from'), len(p.get('bodyText') or '')))
    else:
        print(f"NOT FOUND: {cid}")

for f in found:
    print(f)
