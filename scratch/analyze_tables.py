import csv
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

def analyze_all_tables_in_csv():
    with open('latest_500_all.csv', mode='r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        accenture_table_rows = []
        all_table_rows = []
        for idx, row in enumerate(reader):
            body = row.get('body_normalized', '')
            subj = row.get('subject', '')
            from_e = row.get('from_email', '')
            
            # Check for tables or status or req id
            lines = body.splitlines()
            headers = []
            for l in lines:
                l_str = l.strip()
                if 'req' in l_str.lower() and ('id' in l_str.lower() or 'status' in l_str.lower()):
                    headers.append(l_str)
            
            full = f"{subj} {from_e} {body}".lower()
            if 'accenture' in full:
                accenture_table_rows.append((idx, subj, from_e, body))
            if headers:
                all_table_rows.append((idx, subj, from_e, headers, body))

    print(f"Total Accenture rows in latest_500_all.csv: {len(accenture_table_rows)}")
    for idx, subj, from_e, body in accenture_table_rows:
        print(f"--- Accenture Row {idx} ---")
        print(f"Subj: {subj}")
        print(f"From: {from_e}")
        print("Body:")
        print(body[:1500])
        print("="*60)

    print(f"\nTotal rows with headers matching 'req' and ('id' or 'status'): {len(all_table_rows)}")
    for idx, subj, from_e, headers, body in all_table_rows:
        print(f"--- Table Row {idx} ---")
        print(f"Subj: {subj}")
        print(f"From: {from_e}")
        print(f"Headers found: {headers}")
        print("Body snippet:")
        print(body[:1000])
        print("="*60)

if __name__ == '__main__':
    analyze_all_tables_in_csv()
