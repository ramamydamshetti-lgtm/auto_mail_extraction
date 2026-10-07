import json
import sys
import os
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

body_obj = msg.get('body', {}) or {}
body = body_obj.get('content', '')

soup = BeautifulSoup(body, 'html.parser')
tables = soup.find_all('table')
print(f"Total HTML tables: {len(tables)}")

for idx, tbl in enumerate(tables[:10]): # Print first 10 tables
    print(f"\n================ TABLE #{idx+1} ================")
    for tr_idx, tr in enumerate(tbl.find_all('tr')):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(['th', 'td'])]
        print(f" Row #{tr_idx+1} ({len(cells)} cells): {cells}")
