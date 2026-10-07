import csv
import json

with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

print(f"Total emails in latest_500_all.csv: {len(rows)}")
print(f"CSV Headers: {fieldnames}")
if rows:
    print("Sample row 0 keys/vals:")
    sample = {k: str(rows[0][k])[:100] for k in rows[0]}
    print(json.dumps(sample, indent=2))
