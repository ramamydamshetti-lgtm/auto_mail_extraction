import csv
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=== CHECKING LATEST_500_ALL.CSV ===")
with open('latest_500_all.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    csv_rows = list(reader)

print(f"Total rows in latest_500_all.csv: {len(csv_rows)}")

accenture_in_csv = []
for idx, r in enumerate(csv_rows):
    full = (r.get('subject', '') + ' ' + r.get('from_email', '') + ' ' + r.get('body_normalized', '')).lower()
    if 'accenture' in full or '195398-1' in full or 'request-id' in full or 'anusha' in full:
        accenture_in_csv.append((idx, r))

print(f"Rows matching accenture/request-id/anusha in latest_500_all.csv: {len(accenture_in_csv)}")

for idx, r in accenture_in_csv:
    print(f"Row {idx} | Subj={r.get('subject')} | From={r.get('from_email')}")
