import sqlite3
import json
import sys
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from requirement_parser import extract_req_id_table_requirements, parse_requirements_from_email
from client_detector import detect_client
from config import Settings

db_reqs = str(ROOT / "data" / "metaforge_requirements.db")
db_proc = str(ROOT / "data" / "processed_messages.db")

conn_proc = sqlite3.connect(db_proc)
conn_proc.row_factory = sqlite3.Row

conn_reqs = sqlite3.connect(db_reqs)
conn_reqs.row_factory = sqlite3.Row

# Get all pending_reviews and processed messages
rows_pending = conn_proc.execute("SELECT * FROM pending_reviews").fetchall()
rows_processed = conn_proc.execute("SELECT * FROM processed").fetchall()

print(f"Loaded {len(rows_pending)} pending_reviews rows, {len(rows_processed)} processed rows.")

day_counters = {}
seen_keys = set()
total_synced = 0

all_records = []

for r in rows_pending:
    try:
        p = json.loads(r["payload_json"])
        all_records.append(p)
    except Exception:
        pass

for r in rows_processed:
    try:
        p = json.loads(r["payload_json"]) if "payload_json" in r.keys() else {}
        if p and p not in all_records:
            all_records.append(p)
    except Exception:
        pass

print(f"Total raw requirement payloads to process across all clients: {len(all_records)}")

# Re-build metaforge_requirements table cleanly with full client dataset
conn_reqs.execute("DELETE FROM metaforge_requirements")
conn_reqs.commit()

inserted_rows = []

for payload in all_records:
    body = payload.get("bodyText") or payload.get("body") or payload.get("email_body") or ""
    subject = payload.get("email_subject") or payload.get("subject") or ""
    from_addr = payload.get("from") or payload.get("client_lead_poc") or payload.get("client_poc") or ""
    recv_time = payload.get("receivedDateTime") or payload.get("received_date_time") or payload.get("email_received_iso") or "2026-09-30T05:56:00Z"
    date_str = recv_time[:10].replace("/", "-") if len(recv_time) >= 10 else "2026-09-30"

    # Client resolution
    c_name = payload.get("requirement_from", "")
    cm = detect_client(subject, body, from_addr)
    if cm and cm.display_name != "unresolved":
        client_display = cm.display_name
    elif c_name and c_name != "unresolved":
        client_display = c_name
    else:
        client_display = "Other company / source"

    payload["requirement_from"] = client_display

    # Extract table items if available
    items = extract_req_id_table_requirements(body, subject=subject, from_email=from_addr)
    if items:
        for item in items:
            cid = item.req_id.strip("[]()")
            cid_key = f"{date_str}_{cid}_{client_display}"
            if cid_key in seen_keys:
                continue
            seen_keys.add(cid_key)

            day_counters[date_str] = day_counters.get(date_str, 0) + 1
            internal_id = f"{date_str}-{day_counters[date_str]:03d}"

            item_payload = dict(payload)
            item_payload["job_id"] = internal_id
            item_payload["client_jd_id"] = cid
            item_payload["job_title"] = item.job_title
            item_payload["requirement_from"] = client_display
            item_payload["job_status"] = item.raw_status.lower() if item.raw_status else "open"
            item_payload["mandatory_skills"] = item.mandatory_skills
            item_payload["location"] = ", ".join(item.location) if isinstance(item.location, list) else str(item.location)
            item_payload["experience"] = item.experience
            item_payload["budget"] = item.budget
            item_payload["receivedDateTime"] = recv_time
            item_payload["demand_received_date"] = date_str

            conn_reqs.execute(
                "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
                (internal_id, json.dumps(item_payload), recv_time)
            )
            inserted_rows.append((internal_id, cid, client_display, item.job_title, item_payload["job_status"]))
    else:
        cid = payload.get("client_jd_id") or payload.get("raw_req_id") or ""
        cid_clean = cid.strip("[]()") if cid else ""
        title = payload.get("job_title") or payload.get("role") or f"{client_display} Requirement"
        cid_key = f"{date_str}_{cid_clean}_{title}"
        if cid_key in seen_keys:
            continue
        seen_keys.add(cid_key)

        day_counters[date_str] = day_counters.get(date_str, 0) + 1
        internal_id = f"{date_str}-{day_counters[date_str]:03d}"

        payload["job_id"] = internal_id
        if cid_clean:
            payload["client_jd_id"] = cid_clean
        payload["receivedDateTime"] = recv_time
        payload["demand_received_date"] = date_str

        conn_reqs.execute(
            "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, ?)",
            (internal_id, json.dumps(payload), recv_time)
        )
        inserted_rows.append((internal_id, cid_clean, client_display, title, payload.get("job_status", "open")))

conn_reqs.commit()
conn_reqs.close()
conn_proc.close()

print(f"\n==========================================")
print(f"FULL PIPELINE EXECUTION COMPLETE!")
print(f"Successfully processed and inserted {len(inserted_rows)} requirement records across ALL clients into metaforge_requirements.db.")
print(f"==========================================\n")
