import sys, os
import json
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))
from outlook_graph import (
    acquire_token_from_env,
    iter_inbox_messages,
)
from body_normalizer import normalize_body, html_to_plain
from job_table_extractor import parse_html_table_roles

token = acquire_token_from_env()
mailbox = os.environ.get("OUTLOOK_MAILBOX", "recruitment.application@metaforgeit.com")

raw_messages = list(iter_inbox_messages(token, mailbox, limit=50))
today_raw = [m for m in raw_messages if "2026-09-30" in (m.get("receivedDateTime") or "")]

print("==========================================================")
print(f"OUTLOOK LIVE INBOX - TODAY'S EMAILS (2026-09-30)")
print("==========================================================\n")

for idx, m in enumerate(today_raw, 1):
    subj = m.get("subject") or "No Subject"
    from_obj = m.get("from") or {}
    ea = from_obj.get("emailAddress") or {} if isinstance(from_obj, dict) else {}
    from_email = (ea.get("address") or "Unknown").strip()
    recv_dt = m.get("receivedDateTime") or ""
    
    print(f"Email #{idx}:")
    print(f"  Time    : {recv_dt}")
    print(f"  From    : {from_email}")
    print(f"  Subject : {subj}")
    
    body_dict = m.get("body") or {}
    html_content = body_dict.get("content") or "" if (body_dict.get("contentType") or "").lower() == "html" else ""
    plain_content = body_dict.get("content") or "" if (body_dict.get("contentType") or "").lower() != "html" else html_to_plain(html_content)
    
    # Check for HTML table demands
    if html_content:
        roles = parse_html_table_roles(html_content)
        if roles:
            print(f"  --> Found {len(roles)} Accenture Open Demands in HTML Table:")
            for r_i, r in enumerate(roles, 1):
                print(f"      {r_i}. Req ID: {r.get('req_id')} | Title: {r.get('role')} | Loc: {r.get('location')} | Exp: {r.get('exp')} | Budget: {r.get('budget')}")
    print()
