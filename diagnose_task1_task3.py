"""
Diagnostic script for Task 1 & Task 3:
Inspects exact raw email content, prompt sent, raw LLM response, post-processing steps, and exact output.
"""

from __future__ import annotations

import json
import logging
from dotenv import load_dotenv
load_dotenv()

import openai
from config import Settings
from requirement_parser import (
    build_parser_system_prompt,
    parse_requirements_from_email,
    _extract_multi_role_rows,
    _extract_requirement_titles_from_thread,
)

logging.basicConfig(level=logging.INFO)

CAPTURED = {}

def patch_openai():
    real_OpenAI = openai.OpenAI
    class DebugOpenAI(real_OpenAI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            orig_create = self.chat.completions.create
            def debug_create(*c_args, **c_kwargs):
                messages = c_kwargs.get("messages", [])
                sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                usr_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                resp = orig_create(*c_args, **c_kwargs)
                raw_content = resp.choices[0].message.content if resp and resp.choices else ""
                CAPTURED["sys_msg"] = sys_msg
                CAPTURED["usr_msg"] = usr_msg
                CAPTURED["raw_content"] = raw_content
                return resp
            self.chat.completions.create = debug_create
    openai.OpenAI = DebugOpenAI

def diagnose_banking_email():
    print("="*80)
    print("TASK 1 DIAGNOSIS: Fw: Requirement - Banking Client - BA & PMO roles")
    print("="*80)
    
    subject = "Fw: Requirement - Banking Client - BA & PMO roles"
    from_email = "rparimi@Kpmg.Com"
    body = """Dear Vendor,
New requirements have been added to Tables.
Please share relevant profiles.

Sr. No | Role | Requirement | Comments
1 | Finops MR (Chennai - 6 or Hyderabad - 1) | GCB 5 | JD Shared
2 | CCR /treasury/Basel 3.1 BA (Gurgaon/Bangalore) | GCB 5 | JD Shared
3 | WDS Design | GCB 4 | JD will be Shared soon
4 | Python programming - finance system operation | GCB 5 | JD Shared
5 | ESG Delivery PM | GCB 4 | JD Shared
"""
    
    print("\n--- 1. Raw Email Content ---")
    print(f"Subject: {subject}")
    print(f"From: {from_email}")
    print(f"Body:\n{body}")
    
    CAPTURED.clear()
    settings = Settings.from_env()
    res = parse_requirements_from_email(subject=subject, body=body, settings=settings)
    
    print("\n--- 2. Final System Prompt Sent (First 300 chars) ---")
    print(CAPTURED.get("sys_msg", "")[:300] + "...")
    
    print("\n--- 3. User Prompt Sent ---")
    print(CAPTURED.get("usr_msg", ""))
    
    print("\n--- 4. Raw LLM Unmodified JSON Response Returned ---")
    print(CAPTURED.get("raw_content", ""))
    
    print("\n--- 5. Final Post-Processed Result ---")
    print(f"Requirements Count: {len(res.requirements)}")
    for idx, r in enumerate(res.requirements, 1):
        print(f"  Req #{idx}: title='{r.job_title}', mandatory_skills={r.mandatory_skills}, soft_skills={r.soft_skills}")

def diagnose_workday_email():
    print("\n" + "="*80)
    print("TASK 3 DIAGNOSIS: WORKDAY | FTE - Urgent Requirements")
    print("="*80)
    
    subject = "WORKDAY | FTE - Urgent Requirements"
    from_email = "recruiter@kpmg.com"
    body = """Hi Team, Please find below open KPMG positions:

Sr. No | Role | Requirement | Comments
1 | Workday Integration SME | 7-8+ yrs exp in Workday Studio | Urgent
2 | SAP ABAP Consultant | 5+ yrs exp in SAP S/4HANA | High Priority
3 | React Developer | 4+ yrs exp, Remote | Immediate
"""

    print("\n--- 1. Raw Email Content ---")
    print(f"Subject: {subject}")
    print(f"Body:\n{body}")

    CAPTURED.clear()
    settings = Settings.from_env()
    
    # Inspect raw LLM vs post-processing
    res = parse_requirements_from_email(subject=subject, body=body, settings=settings)

    print("\n--- 2. Raw LLM Unmodified JSON Response Returned ---")
    print(CAPTURED.get("raw_content", ""))

    print("\n--- 3. Symbolic Post-Processing Checks ---")
    table_rows = _extract_multi_role_rows(body)
    pivot_titles = _extract_requirement_titles_from_thread(subject, body)
    print(f"_extract_multi_role_rows output: {table_rows}")
    print(f"_extract_requirement_titles_from_thread output: {pivot_titles}")

    print("\n--- 4. Final Post-Processed Extracted Roles ---")
    print(f"Requirements Count: {len(res.requirements)}")
    for idx, r in enumerate(res.requirements, 1):
        print(f"  Req #{idx}: title='{r.job_title}', exp='{r.experience}', mandatory_skills={r.mandatory_skills}")

if __name__ == "__main__":
    patch_openai()
    diagnose_banking_email()
    diagnose_workday_email()
