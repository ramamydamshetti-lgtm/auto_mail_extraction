import csv
import json
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def check_latest_500_all():
    print("=================== LATEST_500_ALL.CSV ===================")
    with open('latest_500_all.csv', mode='r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        accenture_rows = []
        for idx, row in enumerate(reader):
            subj = row.get('subject', '')
            body = row.get('body_normalized', '')
            from_e = row.get('from_email', '')
            full = f"{subj} {from_e} {body}".lower()
            if 'accenture' in full:
                accenture_rows.append((idx, subj, from_e, body))
    
    print(f"Total Accenture rows in latest_500_all.csv: {len(accenture_rows)}")
    for idx, subj, from_e, body in accenture_rows:
        print(f"Row {idx}: Subject='{subj}', From='{from_e}'")
        print("Body snippet:")
        print(body[:500])
        print("-" * 50)

def check_raw_emails():
    print("=================== RAW EMAILS ===================")
    if os.path.exists('raw_emails'):
        for f in os.listdir('raw_emails'):
            p = os.path.join('raw_emails', f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                print(f"File {f}: length={len(content)}")
                print(content[:500])
                print("-" * 50)

if __name__ == '__main__':
    check_latest_500_all()
    check_raw_emails()
