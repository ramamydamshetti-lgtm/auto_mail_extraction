import os
import glob
import sqlite3
import json
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

def search_for_accenture_demands():
    print("Searching all files for 'open demands' or 'anusha' or 'accenture' tables...")
    for root, dirs, files in os.walk('.'):
        if '.venv' in root or '.git' in root or '.pytest_cache' in root:
            continue
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith('.pyc') or file.endswith('.exe'):
                continue
            try:
                if file.endswith('.db') or file.endswith('.sqlite'):
                    conn = sqlite3.connect(filepath)
                    cur = conn.cursor()
                    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    for tbl in tables:
                        try:
                            rows = cur.execute(f"SELECT * FROM {tbl}").fetchall()
                            for r in rows:
                                str_r = str(r)
                                if 'anusha' in str_r.lower() or 'accenture open demands' in str_r.lower() or 'req id' in str_r.lower():
                                    print(f"[DB MATCH] {filepath} -> {tbl}: {str_r[:200]}")
                        except Exception:
                            pass
                    conn.close()
                else:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if 'accenture open demands' in content.lower() or 'anusha.k@iexcel.co.in' in content.lower() or 'req id' in content.lower():
                            print(f"[FILE MATCH] {filepath} (len={len(content)})")
            except Exception as e:
                pass

if __name__ == '__main__':
    search_for_accenture_demands()
