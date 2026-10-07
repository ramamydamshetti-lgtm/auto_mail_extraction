import sqlite3, json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT job_id, client_jd_id, created_at, updated_at, field_change_history, payload_json FROM metaforge_requirements').fetchall()
cjd_map = {r['client_jd_id']: r for r in rows if r['client_jd_id']}

req_ids_today = [
    '198381-1', '198377-1', '188662-1', '200134-1', '200964-1', '200968-1', '203502-1', '203421-1',
    '203190-1', '203484-1', '204307-1', '203146-1', '204241-1', '204237-1', '204617-1', '205118-1',
    '206291-1', '206678-1', '186544-1', '207725-1', '187291-1', '187643-1', '187686-1', '187653-1',
    '187663-1', '187654-1', '187657-1', '187664-1', '188848-1', '187655-1', '187651-1', '187638-1',
    '187648-1', '188603-1', '209160-1'
]

print("=== CHECKING ALL 35 DEMANDS FROM TODAY'S EMAIL ===")
existing_count = 0
new_count = 0

for cid in req_ids_today:
    if cid in cjd_map:
        r = cjd_map[cid]
        hist = json.loads(r['field_change_history'] or '[]')
        created = r['created_at']
        p = json.loads(r['payload_json'])
        title = p.get('job_title')
        # Check if created today or previously
        is_created_today = created.startswith('2026-10-01')
        print(f"Req ID {cid:10s} | Job ID: {r['job_id']:16s} | Created: {created[:10]} | Is Brand New: {is_created_today} | Title: {title}")
        if is_created_today:
            new_count += 1
        else:
            existing_count += 1
    else:
        print(f"Req ID {cid:10s} | NOT IN DB")

print(f"\nSummary:")
print(f"Total newly created on 2026-10-01: {new_count}")
print(f"Total existing from prior days (2026-09-30, 2026-09-24, etc.): {existing_count}")
