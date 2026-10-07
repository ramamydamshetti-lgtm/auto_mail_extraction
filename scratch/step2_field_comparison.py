import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import urllib.request
import re
from ui.db import get_requirement
from ui.app import UI_CONFIG

test_ids = [
    '2026/09/30-044',  # Deloitte RQ056293
    '2026/09/30-001',  # Accenture 209160-1
    '2026/09/29-001',  # LTTS
    '2026/09/29-002',  # LTTS
    '2026/09/21-356',  # Deloitte
]

fields_map = [
    ('REQUIREMENT ID', lambda r, p: r.get('req_id')),
    ('CLIENT REQ ID', lambda r, p: r.get('client_jd_id')),
    ('JOB STATUS', lambda r, p: (p.get('job_status') or 'open').upper()),
    ('DEMAND RECEIVED DATE', lambda r, p: p.get('receivedDateTime') or r.get('created_at')),
    ('INTERNAL POC (TO)', lambda r, p: p.get('internal_poc')),
    ('INTERNAL POC EMAIL', lambda r, p: p.get('internal_poc_email') or p.get('to')),
    ('REQUIREMENT FROM', lambda r, p: p.get('requirement_from')),
    ('CLIENT LEAD POC (FROM)', lambda r, p: p.get('client_lead_poc') or p.get('from')),
    ('JOB TITLE', lambda r, p: p.get('job_title')),
    ('MONTHLY BUDGET', lambda r, p: p.get('monthly_budget')),
    ('BUDGET CURRENCY', lambda r, p: p.get('budget_currency')),
    ('NOTICE PERIOD', lambda r, p: p.get('notice_period')),
    ('LOCATION', lambda r, p: p.get('location')),
]

for rid in test_ids:
    rec = get_requirement(UI_CONFIG, rid)
    p = rec.get('payload', {}) if rec else {}
    
    url = f"http://127.0.0.1:5000/requirement/{rid}"
    with urllib.request.urlopen(url) as resp:
        html = resp.read().decode('utf-8')
        
    print(f"\n=======================================================")
    print(f"REQUIREMENT: {rid}")
    print(f"=======================================================")
    for label, getter in fields_map:
        db_val = getter(rec, p)
        m = re.search(rf'<div class="field-label">\s*{re.escape(label)}\s*</div>\s*<div class="field-value[^"]*">\s*(.*?)\s*</div>', html, re.DOTALL)
        ui_val = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else '[NOT FOUND]'
        print(f"  {label:24s} | DB Stored: {str(db_val)[:30]:30s} | Rendered UI: {ui_val}")
