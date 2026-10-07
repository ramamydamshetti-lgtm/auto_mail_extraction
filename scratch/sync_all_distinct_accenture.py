import sqlite3
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from requirement_parser import extract_req_id_table_requirements

db_reqs = r'data\metaforge_requirements.db'
db_proc = r'data\processed_messages.db'

conn_proc = sqlite3.connect(db_proc)
conn_proc.row_factory = sqlite3.Row

conn_reqs = sqlite3.connect(db_reqs)
conn_reqs.row_factory = sqlite3.Row

# Clear existing Accenture rows that were collapsed into single placeholders
conn_reqs.execute("DELETE FROM metaforge_requirements WHERE payload_json LIKE '%Accenture%' OR payload_json LIKE '%anusha.k@iexcel.co.in%'")
conn_reqs.commit()

rows = conn_proc.execute("SELECT * FROM pending_reviews WHERE payload_json LIKE '%anusha.k@iexcel.co.in%'").fetchall()

day_counters = {}
inserted_count = 0
seen_cids = set()

for row in rows:
    payload_raw = json.loads(row["payload_json"])
    body = payload_raw.get("bodyText") or payload_raw.get("body") or payload_raw.get("email_body") or ""
    subject = payload_raw.get("email_subject") or payload_raw.get("subject") or ""
    from_email = payload_raw.get("from") or payload_raw.get("client_lead_poc") or "anusha.k@iexcel.co.in"
    recv_time = payload_raw.get("receivedDateTime") or payload_raw.get("received_date_time") or "2026-09-30T05:56:00Z"
    date_str = recv_time[:10].replace("/", "-")

    items = extract_req_id_table_requirements(body, subject=subject, from_email=from_email)
    print(f"Processing email '{subject}' ({recv_time}) -> {len(items)} items found")

    for item in items:
        cid = item.req_id.strip("[]()")
        # Avoid duplicate insertions across identical email re-sends if client_jd_id is identical
        cid_key = f"{date_str}_{cid}"
        if cid_key in seen_cids:
            continue
        seen_cids.add(cid_key)

        day_counters[date_str] = day_counters.get(date_str, 0) + 1
        new_job_id = f"{date_str}-{day_counters[date_str]:03d}"

        payload = dict(payload_raw)
        payload["job_id"] = new_job_id
        payload["client_jd_id"] = cid
        payload["job_title"] = item.job_title
        payload["requirement_from"] = "Accenture"
        payload["job_status"] = item.raw_status.lower() if item.raw_status else "hold"
        payload["mandatory_skills"] = item.mandatory_skills
        payload["location"] = ", ".join(item.location) if isinstance(item.location, list) else str(item.location)
        payload["experience"] = item.experience
        payload["budget"] = item.budget
        payload["receivedDateTime"] = recv_time
        payload["demand_received_date"] = date_str

        conn_reqs.execute(
            "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
            (new_job_id, json.dumps(payload), recv_time)
        )
        inserted_count += 1
        print(f"  Inserted {new_job_id} | Client ID: {cid} | Role: {item.job_title} | Status: {payload['job_status']}")

conn_reqs.commit()
conn_reqs.close()
conn_proc.close()

print(f"\nSuccessfully inserted {inserted_count} distinct Accenture requirement rows into metaforge_requirements.db!")
