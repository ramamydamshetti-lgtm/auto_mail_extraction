import sys, os, json
sys.path.insert(0, r"g:\Auto_email_extraction (3)-new\Auto_email_extraction")
from dotenv import load_dotenv
load_dotenv(r"g:\Auto_email_extraction (3)-new\Auto_email_extraction\.env")

from outlook_graph import acquire_token_from_env, iter_inbox_messages
from body_normalizer import normalize_body, html_to_plain
from config import Settings
from requirement_parser import parse_requirements_from_email
from main import run_client_table_reconciliation

token = acquire_token_from_env()
mailbox = "recruitment.application@metaforgeit.com"
settings = Settings.from_env()

messages = list(iter_inbox_messages(token, mailbox, limit=5))
today_msg = messages[0]

body_dict = today_msg.get("body") or {}
content = body_dict.get("content") or ""
norm = normalize_body(html_to_plain(content), content)
from_addr = today_msg.get("from", {}).get("emailAddress", {}).get("address", "")
subject = today_msg.get("subject", "")
recv_time = today_msg.get("receivedDateTime", "")

parsed = parse_requirements_from_email(subject=subject, body=norm, settings=settings, from_email=from_addr)
parsed, _ = run_client_table_reconciliation("Accenture", norm, parsed)

print(f"EMAIL SUBJECT: {subject}")
print(f"RECEIVED AT: {recv_time}")
print(f"FROM: {from_addr}")
print(f"TOTAL REQUIREMENTS: {len(parsed.requirements)}\n")

for i, r in enumerate(parsed.requirements, 1):
    rd = r.model_dump()
    req_id = rd.get("client_jd_id") or rd.get("req_id") or "N/A"
    title = rd.get("job_title") or "N/A"
    exp = rd.get("experience") or rd.get("experience_range") or rd.get("overall_experience") or "N/A"
    loc = rd.get("location") or "N/A"
    skills = rd.get("mandatory_skills") or rd.get("primary_skills") or []
    positions = rd.get("number_of_positions") or 1
    print(f"{i:2d}. [{req_id}] {title} | Exp: {exp} | Loc: {loc} | Pos: {positions}")
