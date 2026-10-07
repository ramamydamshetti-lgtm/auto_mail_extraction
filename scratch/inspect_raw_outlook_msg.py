import json
from bs4 import BeautifulSoup

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

print("SUBJECT:", msg.get('subject'))
print("RECEIVED:", msg.get('receivedDateTime'))
print("FROM:", msg.get('from'))
print("TO:", msg.get('toRecipients'))

html = msg.get('body', {}).get('content', '')
soup = BeautifulSoup(html, 'html.parser')
tables = soup.find_all('table')
print(f"Total tables in email: {len(tables)}")
for idx, tbl in enumerate(tables):
    print(f"\n--- TABLE {idx} ---")
    trs = tbl.find_all('tr')
    for tr in trs:
        cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
        print(" ", cells)
