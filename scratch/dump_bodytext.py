import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
row = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = '2026/10/05-011'").fetchone()
p = json.loads(row[0])
with open('scratch/bodytext_011.txt', 'w', encoding='utf-8') as f:
    f.write(p.get('bodyText', ''))
print("Wrote scratch/bodytext_011.txt, length:", len(p.get('bodyText', '')))
