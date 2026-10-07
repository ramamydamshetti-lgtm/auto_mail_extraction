import sqlite3
import json

db_path = r'data\metaforge_requirements.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

hold_cids = {
    '195414-1', '195379-1', '195320-1', '195398-1', '174902-1',
    '203501-1', '203486-1', '203489-1', '203495-1', '200961-1',
    '202411-1', '199199-1', '199098-1', '198326-1'
}

rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
updated = 0

for r in rows:
    p = json.loads(r["payload_json"])
    cid = str(p.get("client_jd_id") or p.get("raw_req_id") or "").strip("[]()")
    if cid in hold_cids:
        p["job_status"] = "hold"
        conn.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?", (json.dumps(p), r["job_id"]))
        print(f"Updated {r['job_id']} ([{cid}]) -> Status: hold")
        updated += 1

conn.commit()
conn.close()
print(f"\nDone! Updated status to 'hold' for {updated} records in metaforge_requirements.db.")
