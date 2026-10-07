import os
import glob
import sqlite3
import json
import pandas as pd

target_date = "2026-09-30"

print("=== 1. SQLite Databases Search ===")
for db_file in glob.glob("**/*.db", recursive=True):
    size = os.path.getsize(db_file)
    print(f"Checking {db_file} (size: {size} bytes)...")
    if size == 0:
        continue
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tables:
            rows = cursor.execute(f"SELECT * FROM {t}").fetchall()
            matches = []
            for r in rows:
                r_dict = dict(r)
                r_str = json.dumps(r_dict, default=str)
                if target_date in r_str or "30/09/2026" in r_str:
                    matches.append(r_dict)
            print(f"  Table '{t}': total rows={len(rows)}, matching 30/09/2026={len(matches)}")
            for m in matches:
                print(f"   - Match: {m.get('client_jd_id') or m.get('job_id') or m.get('id')} | Client: {m.get('requirement_from')} | Title: {m.get('job_title_norm') or m.get('job_title')}")
        conn.close()
    except Exception as e:
        print(f"  Error inspecting {db_file}: {e}")

print("\n=== 2. CSV Files Search ===")
for csv_file in glob.glob("**/*.csv", recursive=True):
    try:
        df = pd.read_csv(csv_file, low_memory=False)
        cols_str = df.astype(str)
        mask = cols_str.apply(lambda row: row.str.contains(target_date, case=False, na=False).any() or row.str.contains("30/09/2026", case=False, na=False).any(), axis=1)
        cnt = mask.sum()
        if cnt > 0:
            print(f"CSV '{csv_file}': matches = {cnt}")
            matched_df = df[mask]
            for idx, r in matched_df.iterrows():
                print(f"  - Row {idx}: {r.to_dict()}")
    except Exception as e:
        pass

print("\n=== 3. JSON Files Search ===")
for json_file in glob.glob("*.json"):
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
            if target_date in content or "30/09/2026" in content:
                print(f"JSON '{json_file}': matches found!")
    except Exception as e:
        pass

print("\n=== 4. Raw Emails / Data Folder Search ===")
if os.path.exists("raw_emails"):
    files = os.listdir("raw_emails")
    matches = [f for f in files if target_date in f or "30/09/2026" in f]
    print(f"raw_emails: total files={len(files)}, matching 30/09/2026={len(matches)}")

if os.path.exists("data"):
    for root, dirs, files in os.walk("data"):
        for f in files:
            p = os.path.join(root, f)
            if target_date in f or "30/09/2026" in f:
                print(f"data file match: {p}")
