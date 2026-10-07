import sys, os
sys.path.insert(0, os.getcwd())
from ui.db import fetch_all_records

records = fetch_all_records({'db_paths': ['data/metaforge_requirements.db', 'data/processed_messages.db']})
print('Total merged records in UI:', len(records))
today_records = [r for r in records if '2026/10/06' in str(r.get('req_id'))]
print(f"Today's records ({len(today_records)}):")
for r in today_records:
    req_id = r.get('req_id')
    cjd = r.get('client_jd_id')
    title = r.get('payload', {}).get('job_title')
    subj = r.get('payload', {}).get('subject') or ''
    sender = r.get('payload', {}).get('from') or r.get('payload', {}).get('client_poc') or ''
    rf = r.get('review_fields')
    st = r.get('source_table')
    print(f"[{st}] {req_id} | {cjd} | sender={sender} | title={title} | subj={subj[:45]} | rev={rf}")
