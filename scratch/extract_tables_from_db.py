import sqlite3
import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()

rows = cur.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%' LIMIT 5").fetchall()

for r in rows:
    p = json.loads(r[4])
    print(f"=== ID={r[0]} | job_id={r[2]} | client_jd_id={r[3]} ===")
    print("Subject:", p.get('subject'))
    print("From:", p.get('from'))
    body_html = p.get('bodyHtml') or ''
    body_text = p.get('bodyText') or ''
    if body_html:
        soup = BeautifulSoup(body_html, 'html.parser')
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables in HTML")
        for idx, tbl in enumerate(tables):
            rows_html = tbl.find_all('tr')
            print(f"Table {idx} has {len(rows_html)} rows")
            for tr in rows_html[:5]:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                print("  ROW:", cells)
    elif body_text:
        print("Body Text snippet:")
        print(body_text[:500])
    print("="*60)

conn.close()
