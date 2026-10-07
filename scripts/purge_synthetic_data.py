import os
import glob
import sqlite3

def main():
    # 1. Delete test files from data/mail-drop
    drop_files = glob.glob('data/mail-drop/*/*')
    print(f"Found drop files: {len(drop_files)}")
    for f in drop_files:
        if 'test_' in f:
            print("Deleting:", f)
            os.remove(f)

    # 2. Delete synthetic rows from metaforge_requirements.db
    con_mf = sqlite3.connect('data/metaforge_requirements.db')
    cur_mf = con_mf.cursor()
    synthetic_jids = ['2026/10/06-005', '2026/10/06-006', '2026/10/07-001']
    for jid in synthetic_jids:
        cur_mf.execute('DELETE FROM metaforge_requirements WHERE job_id = ?', (jid,))
    con_mf.commit()
    print("Purged synthetic rows from metaforge_requirements.db")

    # 3. Delete synthetic rows from processed_messages.db
    con_pm = sqlite3.connect('data/processed_messages.db')
    cur_pm = con_pm.cursor()

    cur_pm.execute("DELETE FROM processed WHERE graph_id LIKE 'file:%'")
    cur_pm.execute("DELETE FROM pipeline_state WHERE graph_id LIKE 'file:%'")
    cur_pm.execute("DELETE FROM seen_messages WHERE graph_id LIKE 'file:%'")
    cur_pm.execute("DELETE FROM email_dispositions WHERE graph_id LIKE 'file:%'")
    cur_pm.execute("DELETE FROM requirement_fingerprints WHERE graph_id LIKE 'file:%'")

    for jid in synthetic_jids:
        cur_pm.execute("DELETE FROM requirement_memory WHERE payload_json LIKE ?", (f"%{jid}%",))
        cur_pm.execute("DELETE FROM client_requirements WHERE payload_json LIKE ?", (f"%{jid}%",))
        cur_pm.execute("DELETE FROM pending_reviews WHERE job_id = ?", (jid,))
        cur_pm.execute("DELETE FROM requirement_identity WHERE original_record_ref = ?", (jid,))

    cur_pm.execute("DELETE FROM client_requirements WHERE client_jd_id = '298412-1'")
    cur_pm.execute("DELETE FROM requirement_identity WHERE client_jd_id = '298412-1' OR identity LIKE '%298412-1%'")
    cur_pm.execute("DELETE FROM pending_reviews WHERE id = 909 OR review_fields LIKE '%ltts:hash:f8169efa2e937fab%'")

    con_pm.commit()
    print("Purged synthetic rows from processed_messages.db")

if __name__ == "__main__":
    main()
