import sys
import sqlite3
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from requirement_parser import extract_req_id_table_requirements
from config import get_client_identity_config

# Connect to DBs
db_reqs = r'data\metaforge_requirements.db'
db_proc = r'data\processed_messages.db'

conn_proc = sqlite3.connect(db_proc)
conn_proc.row_factory = sqlite3.Row

conn_reqs = sqlite3.connect(db_reqs)
conn_reqs.row_factory = sqlite3.Row

# Fetch all accenture emails from pending_reviews and processed
rows = conn_proc.execute("SELECT * FROM pending_reviews").fetchall()

new_inserted = 0

for row in rows:
    payload_raw = json.loads(row["payload_json"])
    body = payload_raw.get("bodyText") or payload_raw.get("body") or payload_raw.get("email_body") or ""
    subject = payload_raw.get("email_subject") or payload_raw.get("subject") or ""
    from_email = payload_raw.get("from") or payload_raw.get("client_lead_poc") or "anusha.k@iexcel.co.in"
    recv_time = payload_raw.get("receivedDateTime") or payload_raw.get("received_date_time") or "2026-09-30T05:56:00Z"

    items = extract_req_id_table_requirements(body, subject=subject, from_email=from_email)
    if not items:
        continue

    print(f"Found {len(items)} table requirements in email '{subject}':")
    for item in items:
        cid = item.req_id.strip("[]()")
        # Check if already present in metaforge_requirements.db
        existing = conn_reqs.execute("SELECT * FROM metaforge_requirements WHERE payload_json LIKE ?", (f"%{cid}%",)).fetchone()
        
        # Prepare payload
        payload = dict(payload_raw)
        payload["client_jd_id"] = cid
        payload["job_title"] = item.job_title
        payload["requirement_from"] = "Accenture"
        payload["job_status"] = item.raw_status.lower() if item.raw_status else "hold"
        payload["mandatory_skills"] = item.mandatory_skills
        payload["location"] = ", ".join(item.location) if isinstance(item.location, list) else str(item.location)
        payload["experience"] = item.experience
        payload["receivedDateTime"] = recv_time
        payload["demand_received_date"] = recv_time[:10]

        if existing:
            # Update existing record
            old_job_id = existing["job_id"]
            conn_reqs.execute("UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?", (json.dumps(payload), old_job_id))
            print(f"  Updated requirement {old_job_id} for client ID {cid} ({item.job_title} | Status: {payload['job_status']})")
        else:
            # Generate new sequence ID
            date_str = recv_time[:10].replace("/", "-")
            count_row = conn_reqs.execute("SELECT count(*) FROM metaforge_requirements WHERE job_id LIKE ?", (f"{date_str}-%",)).fetchone()
            seq_num = (count_row[0] + 1) if count_row else 1
            new_job_id = f"{date_str}-{seq_num:03d}"

            conn_reqs.execute(
                "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
                (new_job_id, json.dumps(payload), recv_time)
            )
            new_inserted += 1
            print(f"  INSERTED requirement {new_job_id} for client ID {cid} ({item.job_title} | Status: {payload['job_status']})")

conn_reqs.commit()
conn_reqs.close()
conn_proc.close()

print(f"\nDone! Sync completed. Inserted/Updated Accenture requirements into database.")
