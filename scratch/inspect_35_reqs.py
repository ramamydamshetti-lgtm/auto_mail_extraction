import sqlite3
import json

conn = sqlite3.connect('file:data/processed_messages.db?mode=ro', uri=True)
gid = 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB9pNT0AAA='
rows = conn.execute('SELECT id, requirement_from, job_title_norm, payload_json, created_at FROM requirement_memory WHERE source_graph_id = ?', (gid,)).fetchall()

print(f"Total rows in requirement_memory: {len(rows)}")
for r in rows:
    p = json.loads(r[3])
    print(f"client_jd_id: {p.get('client_jd_id')}, job_id: {p.get('job_id')}, title: {p.get('job_title')}, location: {p.get('location')}, demand_received_date: {p.get('demand_received_date')}")

conn.close()
