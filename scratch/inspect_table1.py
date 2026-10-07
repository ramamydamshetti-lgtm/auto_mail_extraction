import sqlite3
import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/processed_messages.db')
cur = conn.cursor()

rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()

print(f"Total rows in pending_reviews: {len(rows)}")

accenture_emails = {}
for r in rows:
    p = json.loads(r[0])
    subj = p.get('subject')
    gid = p.get('graphMessageId') or p.get('internetMessageId')
    html = p.get('bodyHtml')
    if gid not in accenture_emails and html:
        accenture_emails[gid] = (subj, p.get('from'), html)

print(f"Found {len(accenture_emails)} distinct Accenture emails with HTML")

for gid, (subj, sender, html) in accenture_emails.items():
    print(f"\n==================================================")
    print(f"Subject: {subj} | From: {sender}")
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    if tables:
        main_table = tables[0]
        trs = main_table.find_all('tr')
        print(f"Main Table 1 has {len(trs)} rows.")
        for idx, tr in enumerate(trs[:10]):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            print(f"  Row {idx}: {cells}")

conn.close()
