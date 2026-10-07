import sys
import sqlite3
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processed_store import ProcessedStore

def main():
    db_dir = Path(__file__).resolve().parent.parent / "data"
    mf_db = db_dir / "metaforge_requirements.db"
    pm_db = db_dir / "processed_messages.db"

    print("=== RECONCILING STOP DEMAND & DUPLICATES ===")
    
    # 1. Remove 2026/10/06-001 (which was wrongly generated from the Oct 6 stop email)
    conn_mf = sqlite3.connect(mf_db)
    conn_mf.execute("DELETE FROM metaforge_requirements WHERE job_id = '2026/10/06-001'")
    conn_mf.execute("DELETE FROM status_history WHERE requirement_id = '2026/10/06-001'")
    conn_mf.commit()
    conn_mf.close()
    print("[1] Removed wrongly generated 2026/10/06-001 from metaforge_requirements.db")

    conn_pm = sqlite3.connect(pm_db)
    conn_pm.execute("DELETE FROM requirement_identity WHERE original_record_ref = '2026/10/06-001' OR identity = 'ltts:hash:d5109143d98a7f83'")
    conn_pm.execute("DELETE FROM client_requirements WHERE client_jd_id = '2026/10/06-001'")
    conn_pm.execute("DELETE FROM status_history WHERE requirement_id = '2026/10/06-001'")
    conn_pm.commit()
    conn_pm.close()
    print("[2] Removed 2026/10/06-001 references from processed_messages.db")

    # 2. Update 2026/09/29-004 to status 'hold' using production ProcessedStore
    stop_gid = "AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB-_z2mAAA="
    with ProcessedStore(pm_db) as store:
        ok = store.update_requirement_status(
            requirement_id="2026/09/29-004",
            new_status="hold",
            source_email_id=stop_gid,
            changed_by="RULE_ENGINE",
        )
        print(f"[3] Updated 2026/09/29-004 status to 'hold': {ok}")
        store.record_email_disposition(
            message_id=stop_gid,
            graph_id=stop_gid,
            internet_message_id="<PNYPR01MB12889C3B50FED22DFFC37DEA0ED952@PNYPR01MB12889.INDPRD01.PROD.OUTLOOK.COM>",
            subject="RE: TPC - Requirement - SMS - MES Product Owner - Bangalore, Chennai, Pune, Mysore, Vadodara, Hyderabad",
            from_email="Kallol.Chakraborty@Ltts.com",
            received_date_time="2026-10-06T01:44:01Z",
            disposition="status_updated",
            reason="status_short_circuit:2026/09/29-004",
        )
        print("[4] Recorded email disposition as status_updated for 2026/09/29-004")

    # Verify state of 2026/09/29-004
    conn_mf = sqlite3.connect(mf_db)
    row = conn_mf.execute("SELECT job_id, client_jd_id, payload_json, updated_at FROM metaforge_requirements WHERE job_id = '2026/09/29-004'").fetchone()
    if row:
        p = json.loads(row[2])
        print(f"[5] Verified 2026/09/29-004 in DB: job_title='{p.get('job_title')}', job_status='{p.get('job_status')}', updated_at='{row[3]}'")
    hist = conn_mf.execute("SELECT from_status, to_status, changed_at, source_email_id, changed_by FROM status_history WHERE requirement_id = '2026/09/29-004'").fetchall()
    print(f"[6] Status history in metaforge_requirements.db: {hist}")
    conn_mf.close()

if __name__ == "__main__":
    main()
