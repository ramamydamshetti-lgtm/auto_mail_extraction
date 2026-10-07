import json
from bs4 import BeautifulSoup

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

html = msg.get('body', {}).get('content', '')
soup = BeautifulSoup(html, 'html.parser')
tables = soup.find_all('table')
for idx in range(min(10, len(tables))):
    print(f"\n--- TABLE {idx} ---")
    trs = tables[idx].find_all('tr')
    for tr in trs:
        cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
        print(" ", cells)
