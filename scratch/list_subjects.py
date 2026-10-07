import csv
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('latest_500_all.csv', mode='r', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    print("Subjects in latest_500_all.csv:")
    all_subjects = []
    for idx, row in enumerate(reader):
        subj = row.get('subject', '')
        from_e = row.get('from_email', '')
        all_subjects.append((idx, subj, from_e))

print(f"Total rows in latest_500_all.csv: {len(all_subjects)}")
for idx, subj, from_e in all_subjects[:30]:
    print(f"Row {idx}: From={from_e} | Subj={subj}")
