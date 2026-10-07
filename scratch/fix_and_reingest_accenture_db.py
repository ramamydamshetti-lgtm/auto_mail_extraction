import json
import sys
import os
import sqlite3
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('.'))
load_dotenv()

from config import Settings
from requirement_parser import parse_requirements_from_email
from field_mapper import map_to_metaforge, EmailContext
from metaforge_api import IdAllocator

settings = Settings.from_env()

# 1. Clear old Accenture rows from metaforge_requirements.db
conn = sqlite3.connect(settings.metaforge_sqlite_path)
cur = conn.cursor()
cur.execute("DELETE FROM metaforge_requirements WHERE payload_json LIKE '%accenture.com%' OR payload_json LIKE '%iexcel.co.in%' OR payload_json LIKE '%Accenture%'")
deleted_count = cur.rowcount
print(f"Deleted {deleted_count} old Accenture rows from metaforge_requirements.db.")
conn.commit()
conn.close()

# 2. Re-ingest the Accenture email with fixed parser
with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

subject = msg.get('subject', '')
body_obj = msg.get('body', {}) or {}
body = body_obj.get('content', '')
from_email = 'anusha.k@iexcel.co.in'
to_email = 'hiring@iexcel.co.in'
cc_email = 'nitu.pant@iexcel.in'

parsed = parse_requirements_from_email(
    subject=subject,
    body=body,
    settings=settings,
    from_email=from_email
)

print(f"\nParsed {len(parsed.requirements)} clean requirement items from email!")

allocator = IdAllocator(settings.metaforge_id_db)
conn = sqlite3.connect(settings.metaforge_sqlite_path)
cur = conn.cursor()

ingested_count = 0
for r in parsed.requirements:
    item_dict = r.model_dump()
    client_jd_id = r.req_id
    
    # Generate sequential job_id
    job_id = allocator.next_job_id()
    
    ctx = EmailContext(
        graph_message_id=msg.get('id', ''),
        internet_message_id=msg.get('internetMessageId', ''),
        to_emails=[to_email],
        cc_emails=[cc_email],
        from_email=from_email,
        from_name="Anusha K"
    )
    
    payload = map_to_metaforge(
        extracted=item_dict,
        ctx=ctx,
        client_display_name="Accenture",
        job_id=job_id,
        client_jd_id=client_jd_id,
        body_text=body,
        email_subject=subject,
        email_body_plain=msg.get('bodyText', ''),
        email_body_html=body,
        email_received_iso=msg.get('receivedDateTime', '')
    )
    
    # Set job_status to raw_status (e.g. Hold or P2)
    raw_st = r.raw_status or "open"
    payload['job_status'] = "hold" if "hold" in raw_st.lower() else ("open" if raw_st.lower() in ("open", "p1", "p2") else raw_st)
    
    cur.execute(
        "INSERT INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?, ?, datetime('now'))",
        (job_id, json.dumps(payload))
    )
    ingested_count += 1

conn.commit()
conn.close()
allocator.close()

print(f"Successfully ingested {ingested_count} accurate Accenture requirements into {settings.metaforge_sqlite_path}!")
