import sys, os
import json
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
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

target_date = "2026-09-30"

print("======================================================================")
print("LIVE OUTLOOK EMAIL PROCESSING & EXTRACTION FOR TODAY (2026-09-30)")
print("======================================================================")

token = acquire_token_from_env()
mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")

settings = Settings.from_env()

raw_messages = list(iter_inbox_messages(token, mailbox, limit=50))
today_raw = [m for m in raw_messages if target_date in (m.get("receivedDateTime") or "")]

print(f"Total Outlook Emails Received Today ({target_date}): {len(today_raw)}\n")

extracted_requirements = []

for idx, raw in enumerate(today_raw, 1):
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
    print(f"  Received : {recv_dt}")
    print(f"  From     : {from_name} <{from_email}>")
    print(f"  Subject  : {subj}")
    print(f"  Client   : {client_name}")

    # Parse requirements using main parser & table reconciler
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
        req_id = req_dict.get("client_jd_id") or req_dict.get("job_id") or "N/A"
        req_from = req_dict.get("requirement_from") or client_name
        loc = req_dict.get("location") or "N/A"
        exp = req_dict.get("experience_range") or req_dict.get("experience") or "N/A"
        skills = req_dict.get("primary_skills") or req_dict.get("mandatory_skills") or []
        
        print(f"    [{r_idx}] Job Title  : {job_title}")
        print(f"        Req ID     : {req_id}")
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
            "client": req_from,
            "location": loc,
            "skills": skills
        })

print("\n======================================================================")
print(f"FINAL SUMMARY FOR OUTLOOK ON TODAY (2026-09-30):")
print(f"  - Total Emails Received in Outlook Inbox Today : {len(today_raw)}")
print(f"  - Total Requirements Extracted Today           : {len(extracted_requirements)}")
print("======================================================================")
