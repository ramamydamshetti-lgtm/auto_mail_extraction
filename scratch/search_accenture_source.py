import sqlite3
import json
import glob

print("=== SEARCHING DBs ===")
conn = sqlite3.connect(r'data\processed_messages.db')
conn.row_factory = sqlite3.Row
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

for t in tables:
    try:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        for r in rows:
            p_str = str(dict(r))
            if "anusha.k@iexcel.co.in" in p_str or "Memory Design" in p_str or "203501-1" in p_str or "195414-1" in p_str:
                p = json.loads(r['payload_json']) if 'payload_json' in r.keys() else {}
                body = p.get('bodyText') or p.get('body') or p.get('email_body') or ""
                print(f"Table '{t}': Found match! ID={r['job_id'] if 'job_id' in r.keys() else 'N/A'}")
                print(f"  Subject: {p.get('subject') or p.get('email_subject')}")
                print(f"  From: {p.get('from') or p.get('client_lead_poc')}")
                print(f"  Body length: {len(body)}")
                if body:
                    print(f"  Body snippet:\n{body[:300]}\n")
    except Exception as e:
        print(f"Error reading table {t}: {e}")

print("=== SEARCHING JSON FILES ===")
json_files = glob.glob("*.json")
for jf in json_files:
    try:
        with open(jf, "r", encoding="utf-8") as f:
            content = f.read()
            if "195414-1" in content or "203501-1" in content or "anusha.k@iexcel.co.in" in content:
                print(f"Found match in JSON file: {jf}")
    except Exception as e:
        pass
