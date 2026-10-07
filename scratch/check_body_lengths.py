import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute('SELECT job_id, payload_json FROM metaforge_requirements')
rows = c.fetchall()

lengths = []
over_2500 = 0
for job_id, p_json in rows:
    try:
        p = json.loads(p_json)
        bt = p.get('bodyText') or ''
        lengths.append((job_id, len(bt)))
        if len(bt) > 2500:
            over_2500 += 1
    except:
        pass

lengths.sort(key=lambda x: x[1], reverse=True)
print(f"Total requirements: {len(lengths)}")
print(f"Requirements with bodyText > 2500 chars: {over_2500} / {len(lengths)} ({over_2500/len(lengths)*100:.1f}%)")
print("\nTop 10 longest emails:")
for jid, l in lengths[:10]:
    print(f"  {jid}: {l} chars")
