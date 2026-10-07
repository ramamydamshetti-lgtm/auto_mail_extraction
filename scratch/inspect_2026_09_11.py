import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = '2026/09/11-001' OR job_id = '2026/09/11-159'")
rows = c.fetchall()
for r in rows:
    p = json.loads(r[2])
    print(f"\n=== RECORD {r[0]} (Client JD ID: {r[1]}) ===")
    for k in sorted(p.keys()):
        if k not in ['bodyText', 'bodyHtml']:
            print(f"  {k:28}: {p[k]}")
