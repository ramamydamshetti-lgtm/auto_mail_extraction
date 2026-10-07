import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()

budget_count = 0
currency_count = 0
clean_np_count = 0

for r in rows:
    p = json.loads(r['payload_json'])
    if p.get('monthly_budget'):
        budget_count += 1
    if p.get('budget_currency'):
        currency_count += 1
    np = str(p.get('notice_period') or '').lower()
    if 'e-mail message' in np:
        clean_np_count += 1

print(f"Total rows: {len(rows)}")
print(f"Rows with monthly_budget: {budget_count}")
print(f"Rows with budget_currency: {currency_count}")
print(f"Rows with contaminated notice_period: {clean_np_count}")

# Check RQ056293
r044 = conn.execute("SELECT * FROM metaforge_requirements WHERE client_jd_id = 'RQ056293'").fetchone()
p044 = json.loads(r044['payload_json'])
print("\nRQ056293 details:")
for k in ['job_id', 'client_jd_id', 'monthly_budget', 'monthly_budget_min', 'monthly_budget_max', 'budget_currency', 'notice_period', 'internal_poc_email', 'receivedDateTime', 'demand_received_date']:
    print(f"  {k}: {p044.get(k)}")

conn.close()
