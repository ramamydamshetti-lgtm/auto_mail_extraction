import sqlite3
import json
import csv
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

def analyze_accenture_email_tables():
    print("=================== ANALYZING ACCENTURE EMAIL TABLES ===================")
    
    # 1. From DB pending_reviews and filtered_log
    conn = sqlite3.connect('data/processed_messages.db')
    cur = conn.cursor()
    
    # Check pending_reviews
    rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()
    print(f"Total pending_reviews payloads matching accenture: {len(rows)}")
    
    all_htmls = []
    seen_graph_ids = set()
    
    for r in rows:
        p = json.loads(r[0])
        gid = p.get('graphMessageId') or p.get('internetMessageId')
        if gid not in seen_graph_ids:
            seen_graph_ids.add(gid)
            html = p.get('bodyHtml') or p.get('bodyText')
            if html:
                all_htmls.append((p.get('subject'), p.get('from'), html))
                
    print(f"Unique Accenture emails extracted: {len(all_htmls)}")
    
    for idx, (subj, sender, html) in enumerate(all_htmls):
        print(f"\n--- EMAIL {idx+1}: Subj='{subj}' | From='{sender}' ---")
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        print(f"Total HTML tables in email: {len(tables)}")
        
        # Print first 3 tables structure
        for t_idx, tbl in enumerate(tables):
            tr_list = tbl.find_all('tr')
            headers = []
            for tr in tr_list:
                ths = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                if ths:
                    headers.append(ths)
            print(f"  Table {t_idx+1} ({len(tr_list)} rows):")
            for h in headers[:4]:
                print(f"    {h}")
            if len(headers) > 4:
                print(f"    ... and {len(headers)-4} more rows")
                
    conn.close()

if __name__ == '__main__':
    analyze_accenture_email_tables()
