import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.request
import re
from ui.db import fetch_all_records
from ui.app import UI_CONFIG

records = fetch_all_records(UI_CONFIG)
print(f"Total loaded records: {len(records)}")

# Pick 6 distinct requirements across clients: Deloitte, LTTS, Accenture, etc.
test_ids = [
    '2026/09/30-044',  # Deloitte RQ056293
    '2026/09/29-001',  # LTTS
    '2026/09/29-002',  # LTTS
    '2026/09/30-046',  # Accenture
    '2026/09/21-356',  # Deloitte
    '2026/09/17-607',  # Deloitte RQ054656
]

for rid in test_ids:
    url = f"http://127.0.0.1:5000/requirement/{rid}"
    try:
        with urllib.request.urlopen(url) as resp:
            html = resp.read().decode('utf-8')
            
            def get_f(f_name):
                m = re.search(rf'<div class="field-label">\s*{re.escape(f_name)}\s*</div>\s*<div class="field-value[^"]*">\s*(.*?)\s*</div>', html, re.DOTALL)
                return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else '[MISSING]'
                
            print(f"\n=== {rid} ===")
            print(f"  Title: {get_f('JOB TITLE')}")
            print(f"  Client: {get_f('REQUIREMENT FROM')}")
            print(f"  Received: {get_f('DEMAND RECEIVED DATE')}")
            print(f"  Monthly Budget: {get_f('MONTHLY BUDGET')}")
            print(f"  Currency: {get_f('BUDGET CURRENCY')}")
            print(f"  Notice Period: {get_f('NOTICE PERIOD')}")
    except Exception as e:
        print(f"Failed {rid}: {e}")
