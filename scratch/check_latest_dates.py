import sys
import os
import json
import csv
import sqlite3

print("=== Checking latest dates in latest_500_all.csv ===")
if os.path.exists("latest_500_all.csv"):
    with open("latest_500_all.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        dates = [row.get("received_date_time", "")[:10] for row in reader if row.get("received_date_time")]
        print(f"Total rows in CSV: {len(dates)}")
        if dates:
            dates.sort(reverse=True)
            print("Latest 5 dates in CSV:", dates[:5])

print("\n=== Checking latest dates in metaforge_requirements.db ===")
if os.path.exists("data/metaforge_requirements.db"):
    conn = sqlite3.connect("data/metaforge_requirements.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT created_at FROM metaforge_requirements ORDER BY created_at DESC LIMIT 5").fetchall()
    print("Latest 5 created_at in metaforge_requirements:", rows)

print("\n=== Checking latest dates in requirement_memory ===")
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT created_at FROM requirement_memory ORDER BY created_at DESC LIMIT 5").fetchall()
    print("Latest 5 created_at in requirement_memory:", rows)
