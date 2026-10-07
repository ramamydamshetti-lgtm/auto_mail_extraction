import sys, os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r"g:\Auto_email_extraction (3)-new\Auto_email_extraction\.env")
sys.path.insert(0, r"g:\Auto_email_extraction (3)-new\Auto_email_extraction")

from outlook_graph import (
    acquire_token_from_env,
    iter_inbox_messages,
    message_to_outlook
)
from body_normalizer import normalize_body, html_to_plain
from client_detector import detect_client
from config import Settings
from requirement_parser import parse_requirements_from_email
from main import run_client_table_reconciliation
from intake_gates import pre_classify_block_reason

ist_tz = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(ist_tz)
today_ist = now_ist.strftime("%Y-%m-%d")
today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

print("======================================================================")
print(f"LIVE OUTLOOK EMAIL PROCESSING FOR TODAY ({today_ist} IST / {today_utc} UTC)")
print("======================================================================\n")

token = acquire_token_from_env()
mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")
settings = Settings.from_env()

# Retrieve recent messages
raw_messages = list(iter_inbox_messages(token, mailbox, limit=100))

# Filter for today's messages (checking both UTC and IST date representation)
today_raw = []
for m in raw_messages:
    recv_dt = m.get("receivedDateTime") or ""
    if not recv_dt:
        continue
    # parse timestamp
    try:
        dt_utc = datetime.fromisoformat(recv_dt.replace("Z", "+00:00"))
        dt_ist = dt_utc.astimezone(ist_tz)
        if dt_ist.strftime("%Y-%m-%d") == today_ist or dt_utc.strftime("%Y-%m-%d") == today_ist:
            today_raw.append((m, dt_ist, dt_utc))
    except Exception:
        if today_ist in recv_dt or today_utc in recv_dt:
            today_raw.append((m, None, None))

print(f"Total Outlook Emails Received Today ({today_ist}): {len(today_raw)}\n")

extracted_requirements = []

for idx, item in enumerate(today_raw, 1):
    raw, dt_ist, dt_utc = item
    gid = raw.get("id") or ""
    subj = raw.get("subject") or ""
    from_obj = raw.get("from") or {}
    ea = from_obj.get("emailAddress") or {} if isinstance(from_obj, dict) else {}
    from_email = (ea.get("address") or "").strip()
    from_name = (ea.get("name") or "").strip()
    recv_dt = raw.get("receivedDateTime") or ""
    body_dict = raw.get("body") or {}
    body_content = body_dict.get("content") or ""
    content_type = body_dict.get("contentType") or "text"

    plain = body_content if content_type.lower() != "html" else html_to_plain(body_content)
    html_body = body_content if content_type.lower() == "html" else ""
    body_norm = normalize_body(plain, html_body)
    
    client = detect_client(subj, body_norm, from_email)
    client_name = client.display_name if client else "Unknown"

    print(f"==================================================")
    print(f"Email #{idx}:")
    ist_str = dt_ist.strftime("%Y-%m-%d %I:%M:%S %p IST") if dt_ist else recv_dt
    print(f"  Received : {recv_dt} ({ist_str})")
    print(f"  From     : {from_name} <{from_email}>")
    print(f"  Subject  : {subj}")
    print(f"  Client   : {client_name}")

    # Check block reason
    block = pre_classify_block_reason(from_email, subj, body_norm)
    if block:
        print(f"  Intake Gate: BLOCKED ({block})")
        continue

    # Parse requirements using parser & table reconciler
    parsed = parse_requirements_from_email(
        subject=subj,
        body=body_norm,
        settings=settings,
        message_id=gid or None,
        from_email=from_email
    )
    
    parsed, recon_meta = run_client_table_reconciliation(
        client_name=client_name,
        body_text=body_norm,
        parse_result=parsed,
        graph_id=gid
    )

    print(f"  Requirements Extracted: {len(parsed.requirements)}")
    for r_idx, req in enumerate(parsed.requirements, 1):
        req_dict = req.model_dump()
        job_title = req_dict.get("job_title")
        req_id = req_dict.get("client_jd_id") or req_dict.get("req_id") or req_dict.get("job_id") or "N/A"
        req_from = req_dict.get("requirement_from") or client_name
        loc = req_dict.get("location") or "N/A"
        exp = req_dict.get("experience_range") or req_dict.get("experience") or req_dict.get("overall_experience") or "N/A"
        skills = req_dict.get("primary_skills") or req_dict.get("mandatory_skills") or []
        positions = req_dict.get("number_of_positions") or 1
        
        print(f"    [{r_idx}] Job Title  : {job_title}")
        print(f"        Req ID     : {req_id}")
        print(f"        Positions  : {positions}")
        print(f"        Client     : {req_from}")
        print(f"        Location   : {loc}")
        print(f"        Exp        : {exp}")
        print(f"        Skills     : {skills}")
        
        extracted_requirements.append({
            "email_idx": idx,
            "subject": subj,
            "from_email": from_email,
            "received_at": recv_dt,
            "job_title": job_title,
            "req_id": req_id,
            "positions": positions,
            "client": req_from,
            "location": loc,
            "skills": skills
        })

print("\n======================================================================")
print(f"FINAL SUMMARY FOR OUTLOOK ON TODAY ({today_ist}):")
print(f"  - Total Emails Received in Outlook Inbox Today : {len(today_raw)}")
print(f"  - Total Requirements Extracted Today           : {len(extracted_requirements)}")
print("======================================================================")
