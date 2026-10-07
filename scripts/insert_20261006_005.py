import sqlite3
import json

def main():
    con_pm = sqlite3.connect('data/processed_messages.db')
    cur_pm = con_pm.cursor()
    row = cur_pm.execute('SELECT payload_json, graph_id, created_at, identity FROM pending_reviews WHERE id = 907').fetchone()
    if not row:
        print("Row 907 not found in pending_reviews")
        return
    p = json.loads(row[0])
    gid = row[1]
    ca = row[2]
    ident = row[3] or p.get('identity')

    p['job_id'] = '2026/10/06-005'
    p['req_date'] = '2026/10/06'
    p['seq'] = 5
    p['job_status'] = 'open'
    p['requirement_status'] = 'open'

    p_str = json.dumps(p, ensure_ascii=False)

    con_mf = sqlite3.connect('data/metaforge_requirements.db')
    cur_mf = con_mf.cursor()
    cur_mf.execute('''
        INSERT OR REPLACE INTO metaforge_requirements (
            job_id, payload_json, created_at, client_jd_id, updated_at,
            field_change_history, identity, req_date, seq
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('2026/10/06-005', p_str, ca, p.get('client_jd_id'), ca, json.dumps([]), ident, '2026/10/06', 5))
    con_mf.commit()
    con_mf.close()

    cur_pm.execute("UPDATE pending_reviews SET status = 'RESOLVED', job_id = '2026/10/06-005' WHERE id = 907")
    cur_pm.execute("UPDATE pipeline_state SET state = 'synced', detail = 'synced_to_metaforge' WHERE graph_id = ?", (gid,))
    cur_pm.execute("UPDATE email_dispositions SET disposition = 'extracted' WHERE graph_id = ?", (gid,))
    con_pm.commit()
    con_pm.close()

    print("Successfully inserted 2026/10/06-005 into metaforge_requirements.db and updated processed_messages.db!")

if __name__ == "__main__":
    main()
