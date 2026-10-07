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

settings = Settings.from_env()

print("=================================================================")
print(" MANDATORY VERIFICATION OUTPUT — TWO DIFFERENT CLIENTS")
print("=================================================================")

# -----------------------------------------------------------------
# CLIENT 1: Deloitte / Idexcel ("New Requirement - Control & Monitoring RQ056293")
# -----------------------------------------------------------------
print("\n-----------------------------------------------------------------")
print(" CLIENT 1: Deloitte / Idexcel")
print(" EMAIL SUBJECT: New Requirement - Control & Monitoring RQ056293 (Prasad's Team)")
print(" SENDER: vaishnavi.g@idexcel.com")
print("-----------------------------------------------------------------")

deloitte_body = """Job Posting ID: RQ056293
Role: Control & Monitoring Specialist
Experience: 9+ years of experience
Location: Hyderabad / Bangalore
Budget: 2200000 - 2800000 INR
Mandatory Skills: Internal Controls, SOX Compliance, Risk Assessment
Notice Period: Immediate to 30 days"""

deloitte_parsed = parse_requirements_from_email(
    subject="New Requirement - Control & Monitoring RQ056293 (Prasad's Team)",
    body=deloitte_body,
    settings=settings,
    from_email="vaishnavi.g@idexcel.com"
)

deloitte_item = deloitte_parsed.requirements[0].model_dump() if deloitte_parsed.requirements else {}

ctx_deloitte = EmailContext(
    graph_message_id="MSG-DELOITTE-TEST-1",
    internet_message_id="",
    to_emails=["offshorejobs@metaforgeit.com"],
    cc_emails=[],
    from_email="vaishnavi.g@idexcel.com",
    from_name="Vaishnavi"
)

deloitte_payload = map_to_metaforge(
    extracted=deloitte_item,
    ctx=ctx_deloitte,
    client_display_name="Deloitte",
    job_id="2026/09/30-044",
    client_jd_id="RQ056293",
    body_text=deloitte_body,
    email_subject="New Requirement - Control & Monitoring RQ056293 (Prasad's Team)",
    email_body_plain=deloitte_body,
    email_received_iso="2026-09-30T10:00:00Z"
)

print(json.dumps(deloitte_payload, indent=2))

# -----------------------------------------------------------------
# CLIENT 2: Accenture / iExcel ("Don't work on below requirement")
# -----------------------------------------------------------------
print("\n-----------------------------------------------------------------")
print(" CLIENT 2: Accenture / iExcel")
print(" EMAIL SUBJECT: Don't work on below requirement")
print(" SENDER: anusha.k@iexcel.co.in")
print("-----------------------------------------------------------------")

accenture_body = """Please don't work on below requirement. Put on Hold immediately.
Req ID: 203483-1 | Grade 9 | Salesforce Omnistudio Platform | Bangalore(BDC-7) | RTO | 2.79 Lakhs | 5 Yrs | Any Graduation | Hold"""

accenture_parsed = parse_requirements_from_email(
    subject="Don't work on below requirement",
    body=accenture_body,
    settings=settings,
    from_email="anusha.k@iexcel.co.in"
)

accenture_item = accenture_parsed.requirements[0].model_dump() if accenture_parsed.requirements else {}

ctx_accenture = EmailContext(
    graph_message_id="MSG-ACCENTURE-TEST-1",
    internet_message_id="",
    to_emails=["hiring@iexcel.co.in"],
    cc_emails=["nitu.pant@iexcel.in"],
    from_email="anusha.k@iexcel.co.in",
    from_name="Anusha K"
)

accenture_payload = map_to_metaforge(
    extracted=accenture_item,
    ctx=ctx_accenture,
    client_display_name="Accenture",
    job_id="2026/09/30-050",
    client_jd_id="203483-1",
    body_text=accenture_body,
    email_subject="Don't work on below requirement",
    email_body_plain=accenture_body,
    email_received_iso="2026-09-30T10:15:00Z"
)

print(json.dumps(accenture_payload, indent=2))
