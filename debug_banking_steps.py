"""
Print exact LLM response and requirements at every stage of parse_requirements_from_email.
"""

from __future__ import annotations

import json
import logging
from dotenv import load_dotenv
load_dotenv()

from config import Settings
from requirement_parser import parse_requirements_from_email

logging.basicConfig(level=logging.INFO)

def debug_full_banking_pipeline():
    subject = "Fw: Requirement - Banking Client - BA & PMO roles"
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
    settings = Settings.from_env()
    parse_res = parse_requirements_from_email(subject=subject, body=body, settings=settings)
    print(f"\n--- PARSER RESULT ({len(parse_res.requirements)} items) ---")
    print(f"overall_confidence: {parse_res.overall_confidence}")
    print(f"is_multi_role: {parse_res.is_multi_role}")
    print(f"processing_note: {parse_res.processing_note}")
    for idx, r in enumerate(parse_res.requirements, 1):
        print(f"  Req #{idx}: title='{r.job_title}', mandatory_skills={r.mandatory_skills}, exp='{r.experience}', loc={r.location}")

if __name__ == "__main__":
    debug_full_banking_pipeline()
