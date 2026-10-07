import sqlite3
import json

c2 = sqlite3.connect('data/processed_messages.db')
print('=== processed table ===')
cols = [r[1] for r in c2.execute('PRAGMA table_info(processed)').fetchall()]
print('processed cols:', cols)

print('\n=== pending_reviews: all rows ===')
rows_pr = c2.execute('SELECT id, graph_id, client_jd_id, payload_json FROM pending_reviews').fetchall()
print(f'Total pending_reviews: {len(rows_pr)}')
for r in rows_pr:
    p = json.loads(r[3])
    sender = p.get('from') or p.get('source_from_email') or ''
    subj = p.get('subject') or p.get('source_subject') or ''
    print(f'PR id={r[0]}, client_jd_id={r[2]}, sender={sender}, subj={subj[:60]}')

print('\n=== metaforge_requirements: metaforgeit.com senders ===')
c1 = sqlite3.connect('data/metaforge_requirements.db')
rows_mr = c1.execute('SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements').fetchall()
mf_mr = []
for r in rows_mr:
    p = json.loads(r[2])
    sender = p.get('from') or p.get('source_from_email') or p.get('client_poc') or ''
    if 'metaforgeit.com' in sender and sender != 'rkarnam@metaforgeit.com':
        mf_mr.append((r[0], r[1], sender, (p.get('source_subject') or p.get('subject') or '')[:40]))
print(f'Count in metaforge_requirements from metaforgeit (non-rkarnam): {len(mf_mr)}')
for r in mf_mr[:10]:
    print(r)
