"""Diagnostic: understand current DB state for Rules 1-4 implementation."""
import sqlite3
import json

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row

total = conn.execute('SELECT COUNT(*) FROM metaforge_requirements').fetchone()[0]
print("Total rows:", total)

cols = [r[1] for r in conn.execute('PRAGMA table_info(metaforge_requirements)').fetchall()]
print("Columns:", cols)

# Find rows with actual field change history
rows_with_history = conn.execute(
    """SELECT job_id, client_jd_id, updated_at, field_change_history
       FROM metaforge_requirements
       WHERE field_change_history IS NOT NULL AND field_change_history != '[]'
       LIMIT 10"""
).fetchall()
print("Rows with field change history:", len(rows_with_history))
for r in rows_with_history[:3]:
    hist = json.loads(r['field_change_history'])
    jid = r['job_id']
    cjd = r['client_jd_id']
    upd = r['updated_at']
    print(f"  job_id={jid}, cjd={cjd}, changes={len(hist)}, updated_at={upd}")

# Sample rows with real client_jd_id sorted by updated_at
recent = conn.execute(
    """SELECT job_id, client_jd_id, created_at, updated_at, field_change_history, payload_json
       FROM metaforge_requirements
       WHERE client_jd_id IS NOT NULL AND client_jd_id != ''
       ORDER BY updated_at DESC
       LIMIT 20"""
).fetchall()
print("\nRecent rows with client IDs:")
for r in recent:
    hist_len = 0
    if r['field_change_history']:
        try:
            hist_len = len(json.loads(r['field_change_history']))
        except:
            pass
    jid = r['job_id']
    cjd = r['client_jd_id']
    created = str(r['created_at'])[:19] if r['created_at'] else None
    upd = str(r['updated_at'])[:19] if r['updated_at'] else None
    print(f"  job_id={jid}, cjd={cjd}, created={created}, updated={upd}, history_events={hist_len}")

# Show 2 requirements that have history events - full detail
print("\n--- Requirements with actual change history ---")
for r in rows_with_history[:2]:
    jid = r['job_id']
    cjd = r['client_jd_id']
    print(f"\nREQ: job_id={jid}, client_jd_id={cjd}")
    payload = json.loads(r['payload_json'] if 'payload_json' in r.keys() else '{}')
    hist = json.loads(r['field_change_history'])
    for h in hist:
        print(f"  Changed at: {h.get('changed_at')}")
        for field, chg in h.get('changes', {}).items():
            print(f"    {field}: {repr(chg.get('old'))} -> {repr(chg.get('new'))}")

# Check if updated_at is actually different from created_at for any row
diff_count = conn.execute(
    """SELECT COUNT(*) FROM metaforge_requirements
       WHERE updated_at IS NOT NULL AND updated_at != created_at"""
).fetchone()[0]
print(f"\nRows where updated_at != created_at: {diff_count}")

# Get distinct clients
clients = conn.execute(
    """SELECT DISTINCT json_extract(payload_json, '$.requirement_from') as client
       FROM metaforge_requirements LIMIT 20"""
).fetchall()
print("\nDistinct clients:", [r['client'] for r in clients])

conn.close()
