import glob
import json
import csv
import os

print("=== CHECKING ALL RAW EMAILS / FETCHED FILES FOR ACCENTURE TODAY (2026-09-29) ===")

files_to_check = [
    "raw_emails",
    "today_fetch.csv",
    "latest_200.json",
    "latest_500_all.json",
    "extractions.json",
    "extractions.csv"
]

for item in files_to_check:
    if os.path.isdir(item):
        eml_files = glob.glob(f"{item}/**/*.*", recursive=True)
        print(f"\nFound {len(eml_files)} files in directory '{item}'")
        for fpath in eml_files[:10]:
            print("  ", fpath)
    elif os.path.exists(item):
        size = os.path.getsize(item)
        print(f"\nFile '{item}' size: {size} bytes")
        if item.endswith(".json"):
            try:
                with open(item, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        today_acc = []
                        for row in data:
                            blob = json.dumps(row).lower()
                            if ("accenture" in blob or "iexcel.co.in" in blob or "anusha" in blob) and ("2026-09-29" in blob or "sep 29, 2026" in blob or "29-sep-2026" in blob):
                                today_acc.append(row)
                        print(f"  Matching Accenture 2026-09-29 records in {item}: {len(today_acc)}")
                        for idx, r in enumerate(today_acc[:5], 1):
                            if isinstance(r, dict):
                                print(f"    {idx}. Subject/Title: {r.get('subject') or r.get('job_title') or r.get('req_id')}")
            except Exception as e:
                print(f"  Error reading {item}: {e}")
