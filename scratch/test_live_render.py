import urllib.request
import re

url = 'http://127.0.0.1:5000/requirement/2026/09/30-044'
with urllib.request.urlopen(url) as response:
    html = response.read().decode('utf-8')
    print('HTTP Status:', response.status)

fields_to_check = [
    'REQUIREMENT ID',
    'CLIENT REQ ID',
    'JOB STATUS',
    'DEMAND RECEIVED DATE',
    'INTERNAL POC (TO)',
    'INTERNAL POC EMAIL',
    'REQUIREMENT FROM',
    'CLIENT LEAD POC (FROM)',
    'CLIENT POC (FROM/CC)',
    'JOB TITLE',
    'CLOSED DATE',
    'TYPE OF DEMAND',
    'PRIORITY',
    'NUMBER OF POSITIONS',
    'EXPERIENCE LEVEL',
    'OVERALL EXPERIENCE',
    'EMPLOYMENT TYPE',
    'WORK MODE',
    'LOCATION',
    'BUDGET CURRENCY',
    'MONTHLY BUDGET',
    'YEARLY BUDGET',
    'NOTICE PERIOD',
    'OPEN SINCE',
    'SLA',
]

print("\n--- RENDERED HTML FIELD VALUES ---")
for f in fields_to_check:
    pattern = re.compile(rf'<div class="field-label">\s*{re.escape(f)}\s*</div>\s*<div class="field-value[^"]*">\s*(.*?)\s*</div>', re.DOTALL)
    m = pattern.search(html)
    if m:
        # strip tags inside value
        val = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        print(f"  {f:25s}: {val}")
    else:
        print(f"  {f:25s}: [NOT FOUND]")
