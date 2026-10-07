"""
Diagnostic Script for Task: Diagnose why glossary terms and table extraction are failing.
Intercepts API calls to log exact prompts, raw LLM responses, and validation steps cleanly.
"""

from __future__ import annotations

import sys
import json
import logging
from dotenv import load_dotenv
load_dotenv()

import openai
from config import Settings
from glossary import TermGlossary
from requirement_classifier import classify_email
import requirement_parser
from requirement_parser import build_parser_system_prompt, parse_requirements_from_email, _PARSER_SYSTEM

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CAPTURED_CALLS = []

def patch_openai_class():
    """Patches openai.OpenAI class to intercept chat.completions.create calls."""
    real_OpenAI = openai.OpenAI
    
    class DebugOpenAI(real_OpenAI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            original_create = self.chat.completions.create
            
            def debug_create(*c_args, **c_kwargs):
                messages = c_kwargs.get("messages", [])
                sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                usr_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                
                print("\n" + "="*50 + " [RAW LLM PROMPT SENT] " + "="*50)
                print("--- SYSTEM PROMPT (Header snippet) ---")
                print(sys_msg[:300] + "...\n")
                
                if "Additional recognized terminology" in sys_msg:
                    print("--> GLOSSARY SUPPLEMENT FOUND IN SYSTEM PROMPT!")
                    idx = sys_msg.find("Additional recognized terminology")
                    print(sys_msg[idx:idx+450])
                else:
                    print("--> GLOSSARY SUPPLEMENT NOT FOUND IN SYSTEM PROMPT!")
                    
                print("\n--- USER PROMPT (Full text) ---")
                print(usr_msg)
                
                resp = original_create(*c_args, **c_kwargs)
                
                raw_content = resp.choices[0].message.content if resp and resp.choices else ""
                print("\n" + "="*50 + " [RAW LLM RESPONSE RECEIVED] " + "="*50)
                print(raw_content)
                print("="*123 + "\n")
                
                CAPTURED_CALLS.append({
                    "sys_msg": sys_msg,
                    "usr_msg": usr_msg,
                    "raw_response": raw_content,
                })
                return resp

            self.chat.completions.create = debug_create

    openai.OpenAI = DebugOpenAI

def run_diagnosis_1():
    print("="*80)
    print("DIAGNOSIS 1: Is the glossary prompt supplement actually reaching the API call?")
    print("="*80)
    
    # 1. System prompt inspection
    built_prompt = build_parser_system_prompt()
    glossary_supp = TermGlossary.get_prompt_supplement()
    
    print("\n--- [D1.1] Code & Function Inspection ---")
    print("Exact code in requirement_parser.py's parse_requirements_from_email():")
    print("""
    def _call_model() -> Any:
        system_content = build_parser_system_prompt()
        return client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user},
            ],
            ...
    """)
    print(f"build_parser_system_prompt() total length: {len(built_prompt)} chars")
    print(f"TermGlossary.get_prompt_supplement() total length: {len(glossary_supp)} chars")
    print(f"Is glossary supplement string present in build_parser_system_prompt()? -> {glossary_supp in built_prompt}")

    print("\n--- [D1.2] Live Test on Glossary Term Test Emails ---")
    test_cases = [
        {
            "term": "Buyout",
            "field": "notice_period",
            "subject": "Requirement: Senior Developer - Immediate / Buyout available",
            "body": "Looking for Java Developer with 5 years experience. Immediate joiner or Buyout option available. Budget 15 LPA. Location Bangalore.",
        },
        {
            "term": "SubCon",
            "field": "employment_type",
            "subject": "Need SubCon Java Developer",
            "body": "Role: Java Developer. Experience: 4 years. Employment: SubCon / Contract role. Location: Pune.",
        },
        {
            "term": "Pay Rate",
            "field": "budget",
            "subject": "Urgent Requirement: Python Engineer",
            "body": "Python Engineer needed for 6 month project. Pay Rate: 1200000 per annum. Work location: Remote.",
        },
        {
            "term": "WFH",
            "field": "work_mode",
            "subject": "Urgent Opening: DevOps Engineer (WFH)",
            "body": "DevOps Engineer with AWS and Kubernetes. Work Mode: WFH. Exp: 6 years. Location: Hyderabad.",
        },
    ]

    settings = Settings.from_env()
    
    for case in test_cases:
        print(f"\n>>>>>>> Diagnostic Execution for Term: '{case['term']}' (Target Field: {case['field']}) <<<<<<<")
        
        # Classifier
        cls_res = classify_email(case["body"], subject=case["subject"], settings=settings)
        print(f"Classifier output: label={cls_res.label}, confidence={cls_res.confidence}")
        
        # Parser
        CAPTURED_CALLS.clear()
        try:
            parse_res = parse_requirements_from_email(subject=case["subject"], body=case["body"], settings=settings)
            reqs = parse_res.requirements if parse_res else []
            print(f"Parser returned {len(reqs)} requirement(s). Processing Note: {parse_res.processing_note}")
            if reqs:
                for idx, r in enumerate(reqs, 1):
                    val = getattr(r, case["field"], None)
                    print(f"  Req #{idx} -> job_title='{r.job_title}', extracted_{case['field']}='{val}', confidence={r.confidence}")
                    print(f"  field_sources: {r.field_sources}")
                    print(f"  field_evidence_quotes: {r.field_evidence_quotes}")
                    print(f"  field_extraction_method: {r.field_extraction_method}")
            else:
                print("  RESULT: ZERO REQUIREMENTS EXTRACTED!")
        except Exception as exc:
            print(f"  PARSER EXCEPTION RAISED DURING PROCESSING: {type(exc).__name__}: {exc}")

def run_diagnosis_2():
    print("\n" + "="*80)
    print("DIAGNOSIS 2: Why does the general parser return zero items on table-formatted emails?")
    print("="*80)
    
    table_emails = [
        {
            "name": "WORKDAY | FTE - Urgent Requirements",
            "subject": "WORKDAY | FTE - Urgent Requirements",
            "from_email": "recruiter@kpmg.com",
            "body": """Hi Team, Please find below open KPMG positions:

Sr. No | Role | Requirement | Comments
1 | Workday Integration SME | 7-8+ yrs exp in Workday Studio | Urgent
2 | SAP ABAP Consultant | 5+ yrs exp in SAP S/4HANA | High Priority
3 | React Developer | 4+ yrs exp, Remote | Immediate
"""
        },
        {
            "name": "Fw: Requirement - Banking Client - BA & PMO roles",
            "subject": "Fw: Requirement - Banking Client - BA & PMO roles",
            "from_email": "rparimi@Kpmg.Com",
            "body": """Dear Vendor,
New requirements have been added to Tables.
Please share relevant profiles.

Sr. No | Role | Requirement | Comments
1 | Finops MR (Chennai - 6 or Hyderabad - 1) | GCB 5 | JD Shared
2 | CCR /treasury/Basel 3.1 BA (Gurgaon/Bangalore) | GCB 5 | JD Shared
3 | WDS Design | GCB 4 | JD will be Shared soon
4 | Python programming - finance system operation | GCB 5 | JD Shared
5 | ESG Delivery PM | GCB 4 | JD Shared
"""
        }
    ]

    settings = Settings.from_env()

    for sample in table_emails:
        print(f"\n>>>>>>> Diagnostic Test Case: {sample['name']} <<<<<<<")
        print(f"Subject: {sample['subject']}")
        print(f"From: {sample['from_email']}")
        
        # Classifier
        cls_res = classify_email(sample["body"], subject=sample["subject"], settings=settings, from_email=sample["from_email"])
        print(f"\n[Classifier Decision]")
        print(f"  label: {cls_res.label}, confidence: {cls_res.confidence}")

        # Parser
        CAPTURED_CALLS.clear()
        try:
            parse_res = parse_requirements_from_email(subject=sample["subject"], body=sample["body"], settings=settings)
            print(f"\n[Parser Execution Decision]")
            print(f"  overall_confidence: {parse_res.overall_confidence}")
            print(f"  requirements_count: {len(parse_res.requirements)}")
            print(f"  processing_note: {parse_res.processing_note}")
            print(f"  multi_requirement_note: {parse_res.multi_requirement_note}")
            for idx, r in enumerate(parse_res.requirements, 1):
                print(f"    Req #{idx}: job_title='{r.job_title}', exp='{r.experience}', mandatory_skills={r.mandatory_skills}, location={r.location}")
        except Exception as exc:
            print(f"  PARSER EXCEPTION RAISED DURING PROCESSING: {type(exc).__name__}: {exc}")

        if CAPTURED_CALLS:
            print("\n  [Captured LLM Call Analysis]")
            raw_json = CAPTURED_CALLS[-1]["raw_response"]
            try:
                parsed_data = json.loads(raw_json)
                req_list = parsed_data.get("requirements", [])
                print(f"  Raw LLM returned {len(req_list)} requirement items in JSON:")
                for r_i, item in enumerate(req_list, 1):
                    print(f"    Item #{r_i}: job_title='{item.get('job_title')}', mandatory_skills={item.get('mandatory_skills')}, exp='{item.get('experience')}'")
            except Exception as e:
                print(f"  Raw LLM response failed JSON parsing: {e}")
        else:
            print("  NO LLM CALL WAS MADE BY PARSER!")

if __name__ == "__main__":
    patch_openai_class()
    run_diagnosis_1()
    run_diagnosis_2()
