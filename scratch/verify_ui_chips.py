import urllib.request
import re

html = urllib.request.urlopen('http://127.0.0.1:5000/requirement/2026/10/05-011').read().decode('utf-8')

fields = [
    ("JOB TITLE", r'JOB TITLE</div>\s*<div[^>]*>(.*?)</div>'),
    ("NUMBER OF POSITIONS", r'NUMBER OF POSITIONS</div>\s*<div[^>]*>(.*?)</div>'),
    ("OVERALL EXPERIENCE", r'OVERALL EXPERIENCE</div>\s*<div[^>]*>(.*?)</div>'),
    ("WORK MODE", r'WORK MODE</div>\s*<div[^>]*>(.*?)</div>'),
    ("LOCATION", r'LOCATION</div>\s*<div[^>]*>(.*?)</div>'),
    ("MONTHLY BUDGET", r'MONTHLY BUDGET</div>\s*<div[^>]*>(.*?)</div>'),
    ("YEARLY BUDGET", r'YEARLY BUDGET</div>\s*<div[^>]*>(.*?)</div>'),
    ("NOTICE PERIOD", r'NOTICE PERIOD</div>\s*<div[^>]*>(.*?)</div>'),
]

print("=== UI FIELDS EXTRACTED FROM HTML ===")
for name, pattern in fields:
    m = re.search(pattern, html, re.DOTALL)
    val = m.group(1).strip() if m else "NOT_FOUND"
    print(f"{name}: {val}")

mand = re.findall(r'<span class="skill-chip">(.*?)</span>', html)
print(f"MANDATORY SKILLS ({len(mand)}): {mand}")

add = re.findall(r'<span class="skill-chip skill-chip-secondary">(.*?)</span>', html)
print(f"ADDITIONAL SKILLS ({len(add)}): {add}")
