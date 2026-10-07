import sqlite3, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = '2026/09/07-023' OR former_job_id = '2026/09/07-023'")
r = c.fetchone()
p = json.loads(r[2])
print(f"=== RECORD {r[0]} ===")
for k in sorted(p.keys()):
    if k not in ['bodyText', 'bodyHtml']:
        print(f"  {k:28}: {p[k]}")

body = p.get('bodyText')
print("\n=== RAW EMAIL BODY EXCERPT (first 1000 chars) ===")
print(body[:1000])
print("\n=== RAW EMAIL BODY EXCERPT (last 1000 chars) ===")
print(body[-1000:])
