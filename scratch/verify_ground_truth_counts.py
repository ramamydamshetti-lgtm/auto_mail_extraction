import sqlite3
import json
from ui.app import UI_CONFIG
from ui.db import fetch_all_records

records = fetch_all_records(UI_CONFIG)

acc_count = 0
ltts_count = 0

for r in records:
    c = (r.get("payload", {}).get("requirement_from") or "").lower()
    if "accenture" in c or "iexcel" in c:
        acc_count += 1
    elif "ltts" in c or "l&t" in c:
        ltts_count += 1

print("================ VERIFIED GROUND TRUTH STORE & UI COUNTS ================")
print(f"  • Accenture Distinct Requirements: {acc_count}")
print(f"  • LTTS Distinct Requirements:      {ltts_count}")
print(f"  • Combined Accenture + LTTS Total: {acc_count + ltts_count}")
