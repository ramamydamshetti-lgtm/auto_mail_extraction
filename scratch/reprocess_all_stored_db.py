import sqlite3
import json
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('.'))
load_dotenv()

from config import Settings
from field_mapper import EmailContext, map_to_metaforge
from requirement_parser import parse_requirements_from_email

settings = Settings.from_env()
db_path = settings.metaforge_sqlite_path

print(f"Connecting to database: {db_path}...")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

rows = cur.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements").fetchall()
print(f"Total existing stored requirements in DB: {len(rows)}")

reprocessed_count = 0
cleaned_payloads = []

for job_id, payload_json, created_at in rows:
    p = json.loads(payload_json)
    subj = p.get('subject', '')
    body = p.get('bodyText', '') or p.get('bodyHtml', '')
    from_email = p.get('from', '') or p.get('client_lead_poc', '')
    to_email = p.get('to', '')
    cc_email = p.get('cc', '')
    client_jd_id = p.get('client_jd_id', '')
    client_name = p.get('requirement_from', 'Other')
    
    # Re-parse email with updated universal rules
    parsed = parse_requirements_from_email(
        subject=subj,
        body=body,
        settings=settings,
        from_email=from_email
    )
    
    if parsed.requirements:
        item = parsed.requirements[0].model_dump()
    else:
        item = p # fallback to current if no reparse item
        
    ctx = EmailContext(
        graph_message_id="",
        internet_message_id="",
        to_emails=[to_email] if to_email else [],
        cc_emails=[cc_email] if cc_email else [],
        from_email=from_email,
        from_name=""
    )
    
    updated_p = map_to_metaforge(
        extracted=item,
        ctx=ctx,
        client_display_name=client_name,
        job_id=job_id,
        client_jd_id=client_jd_id,
        body_text=body,
        email_subject=subj,
        email_body_plain=p.get('bodyText', ''),
        email_body_html=p.get('bodyHtml', ''),
        email_received_iso=p.get('receivedDateTime', '')
    )
    
    # Preserve original status and client_jd_id
    updated_p['job_status'] = p.get('job_status', 'open')
    updated_p['client_jd_id'] = p.get('client_jd_id')
    
    cur.execute(
        "UPDATE metaforge_requirements SET payload_json = ? WHERE job_id = ?",
        (json.dumps(updated_p), job_id)
    )
    reprocessed_count += 1

conn.commit()
conn.close()

print(f"Successfully reprocessed {reprocessed_count} existing requirement records in {db_path}.")
