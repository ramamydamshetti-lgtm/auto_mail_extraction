import sqlite3
import json
import sys

db_path = 'data/metaforge_requirements.db'
conn = sqlite3.connect(db_path, timeout=10)
conn.row_factory = sqlite3.Row

r = conn.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = 'RQ056293'").fetchone()
if not r:
    print("Not found", flush=True)
    sys.exit(1)

p = json.loads(r['payload_json'])
print("Before:", flush=True)
print("  monthly_budget:", p.get('monthly_budget'), flush=True)
print("  budget_currency:", p.get('budget_currency'), flush=True)
print("  notice_period:", p.get('notice_period'), flush=True)
print("  skills:", p.get('skills'), flush=True)
print("  internal_poc_email:", p.get('internal_poc_email'), flush=True)
print("  receivedDateTime:", p.get('receivedDateTime'), flush=True)

conn.close()
