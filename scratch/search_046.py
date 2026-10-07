import sqlite3

conn = sqlite3.connect('data/metaforge_requirements.db')
cur = conn.cursor()
rows = cur.execute("SELECT job_id, payload_json FROM metaforge_requirements").fetchall()
print(f"Total rows in metaforge_requirements: {len(rows)}")
for r in rows:
    if '046' in r[0] or '203483-1' in r[1]:
        print("  MATCH:", r[0])
conn.close()
