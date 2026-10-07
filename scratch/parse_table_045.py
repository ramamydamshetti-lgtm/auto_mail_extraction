import sqlite3
import json
from bs4 import BeautifulSoup

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
r = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/09/30-045'").fetchone()
p = json.loads(r['payload_json'])
body = p.get('bodyText') or p.get('body') or ""

soup = BeautifulSoup(body, 'html.parser')
table = soup.find('table')
if table:
    rows = table.find_all('tr')
    for i, row in enumerate(rows):
        cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
        print(f"Row {i}: {cells}")
else:
    print("No table found")
    print(soup.get_text()[:1000])

conn.close()
