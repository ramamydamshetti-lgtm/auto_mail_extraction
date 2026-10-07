import sys, json
sys.path.insert(0, '.')
sys.path.insert(0, 'ui')

with open("ui/config.json") as f:
    UI_CONFIG = json.load(f)

from ui.db import fetch_all_records

recs = fetch_all_records(UI_CONFIG)
print('Total requirements fetched for UI:', len(recs))
if recs:
    print('\nLatest 10 Requirements in UI:')
    for r in recs[:10]:
        p = r.get('payload', {})
        print(f"  ID: {r.get('req_id')} | Client ID: {r.get('client_jd_id')} | Title: {p.get('job_title')} | From: {p.get('requirement_from')} | Received: {r.get('arr_iso')}")
