import csv
import json
import re
import sqlite3

def check_csv(filename):
    print(f"=== Checking {filename} ===")
    with open(filename, mode='r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            text = json.dumps(row).lower()
            if 'accenture' in text or 'req id' in text or 'req_id' in text:
                print(f"Row {idx}: Subject={row.get('subject') or row.get('Subject')}, From={row.get('from_email') or row.get('From')}")

def check_db(db_path):
    print(f"=== Checking DB {db_path} ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for tbl in tables:
        try:
            rows = cur.execute(f"SELECT * FROM {tbl}").fetchall()
            accenture_count = 0
            for r in rows:
                if 'accenture' in str(r).lower():
                    accenture_count += 1
            print(f"Table {tbl}: {len(rows)} rows, {accenture_count} mention accenture")
        except Exception as e:
            print(f"Table {tbl} error: {e}")
    conn.close()

if __name__ == '__main__':
    check_csv('latest_500_all.csv')
    check_csv('today_fetch_2026-04-16.csv')
    check_csv('today_fetch.csv')
    check_db('data/processed_messages.db')
