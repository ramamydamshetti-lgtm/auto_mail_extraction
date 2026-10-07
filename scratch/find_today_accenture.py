import os
import glob
import json
import sqlite3
import csv

print("=== Searching for Accenture demands for 29th Sep ===")

# Search all files for 'Accenture open demands for 29th Sep' or '29th Sep' or 'ACC'
matches = []

for root, dirs, files in os.walk("."):
    if ".venv" in root or ".git" in root or "__pycache__" in root:
        continue
    for fname in files:
        fpath = os.path.join(root, fname)
        if fname.endswith((".json", ".csv", ".txt", ".eml", ".msg", ".db")):
            try:
                if fname.endswith(".db"):
                    conn = sqlite3.connect(fpath)
                    cur = conn.cursor()
                    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    for t in tables:
                        try:
                            rows = cur.execute(f"SELECT * FROM {t} WHERE lower(CAST(payload_json AS TEXT)) LIKE '%accenture%' OR lower(CAST(payload_json AS TEXT)) LIKE '%29th sep%'").fetchall()
                            if rows:
                                print(f"Found {len(rows)} matching rows in {fpath} table {t}")
                        except Exception:
                            pass
                    conn.close()
                else:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                        if "accenture open demands for 29th sep" in text.lower() or ("accenture" in text.lower() and "29" in text):
                            matches.append(fpath)
            except Exception:
                pass

print("\n=== Matching files ===")
for m in matches[:15]:
    print("  ", m)
