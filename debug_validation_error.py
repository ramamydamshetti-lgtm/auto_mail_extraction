"""
Debug ValidationError in RequirementParseResult.model_validate for Banking Client email using Settings.from_env().
"""

from __future__ import annotations

import os
import json
import logging
from dotenv import load_dotenv
load_dotenv()

import openai
from config import Settings
from models import RequirementParseResult
from pydantic import ValidationError
from requirement_parser import build_parser_system_prompt

logging.basicConfig(level=logging.INFO)

def debug_validation_error():
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
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_base = os.getenv("GEMINI_BASE_URL", "").strip()
    llm_model = os.getenv("LLM_MODEL", "").strip() or settings.openai_model
    api_key = gemini_key or settings.openai_api_key

    client = openai.OpenAI(api_key=api_key, base_url=gemini_base or None)
    sys_prompt = build_parser_system_prompt()
    user_prompt = f"Subject:\n{subject}\n\nBody:\n{body}"
    
    resp = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content
    data = json.loads(raw)
    print("--- RAW LLM JSON DATA KEYS ---")
    print(list(data.keys()))
    try:
        RequirementParseResult.model_validate(data)
        print("\nSUCCESS: model_validate passed!")
    except ValidationError as exc:
        print("\nFAILURE: ValidationError caught:")
        print(exc)

if __name__ == "__main__":
    debug_validation_error()
