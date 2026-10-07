import sqlite3
import json
import os
import sys
import re
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from ui.app import UI_CONFIG
from ui.db import get_requirement
from config import Settings, is_strict_field_mapping
from requirement_parser import (
    _latest_thread_segment,
    _strip_candidate_tables,
    _PARSER_USER,
    build_parser_system_prompt,
    STRICT_EXTRACTION_SCHEMA,
    parse_requirements_from_email,
)
from boilerplate_learner import clean_structure_and_extract_boilerplate, validate_skills
from client_detector import detect_client
from field_mapper import map_to_metaforge
from strict_validator import validate_requirement_before_save
from historical_autofill import autofill_from_history
from two_way_verifier import reconcile_two_way
from requirement_comparator import build_requirement_profile

print("======================================================================")
print("TRACE OF 2026/10/05-011 (Power Electronics Hardware Design - Vadodara)")
print("======================================================================")

rec = get_requirement(UI_CONFIG, '2026/10/05-011')
if not rec:
    conn = sqlite3.connect('data/metaforge_requirements.db')
    c = conn.cursor()
    row = c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = '2026/10/05-011'").fetchone()
    if row:
        rec = {"req_id": row[0], "payload": json.loads(row[2])}
    conn.close()

payload = rec.get("payload", {})
raw_body = payload.get("bodyText") or ""
raw_html = payload.get("bodyHtml") or ""
subject = payload.get("subject") or ""
from_email = payload.get("from") or ""

print(f"Req ID in UI     : {rec.get('req_id')}")
print(f"Subject          : {subject}")
print(f"From             : {from_email}")
print(f"Body Length      : {len(raw_body)} chars")

print("\n" + "="*50)
print("STAGE 1: RAW SOURCE EMAIL / BODY")
print("="*50)
print(raw_body)

print("\n" + "="*50)
print("STAGE 2: PREPROCESSING (_latest_thread_segment & _strip_candidate_tables)")
print("="*50)
seg = _latest_thread_segment(raw_body)
print(f"After _latest_thread_segment length: {len(seg)} chars")
cleaned_latest = _strip_candidate_tables(seg)
print(f"After _strip_candidate_tables length: {len(cleaned_latest)} chars")
print("Preprocessed text:")
print(cleaned_latest)

print("\n" + "="*50)
print("STAGE 3: BOILERPLATE REMOVAL (clean_structure_and_extract_boilerplate)")
print("="*50)
client_match = detect_client(subject, cleaned_latest, from_email)
client_name = client_match.display_name if client_match else "generic"
print(f"Detected client: {client_name}")
cleaned_b_text, removed_lines = clean_structure_and_extract_boilerplate(cleaned_latest, client=client_name)
print(f"Cleaned text length: {len(cleaned_b_text)} chars")
print(f"Removed boilerplate lines count: {len(removed_lines)}")
print("Removed boilerplate lines:")
for rl in removed_lines:
    print(f"  - {rl}")
print("\nCleaned text after boilerplate removal:")
print(cleaned_b_text)

print("\n" + "="*50)
print("STAGE 4: FINAL TEXT SENT TO LLM (Prompt)")
print("="*50)
user_prompt = _PARSER_USER.format(subject=subject or "(empty)", body=cleaned_b_text[:2500])
print(f"Prompt length: {len(user_prompt)} chars (b_text slice: {len(cleaned_b_text[:2500])} chars)")
print("User prompt content:")
print(user_prompt)

print("\n" + "="*50)
print("STAGE 5: LLM STRUCTURED OUTPUT")
print("="*50)
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("GEMINI_BASE_URL") or None,
)
resp = client.chat.completions.create(
    model=os.getenv("LLM_MODEL") or "gemini-2.5-flash",
    messages=[
        {"role": "system", "content": build_parser_system_prompt()},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.0,
    max_tokens=2000,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "hiring_requirement_extraction",
            "schema": STRICT_EXTRACTION_SCHEMA,
            "strict": True,
        },
    },
)
raw_llm_str = (resp.choices[0].message.content or "").strip()
print("Raw LLM output:")
print(raw_llm_str)


print("\n" + "="*50)
print("STAGE 6: REQUIREMENT_PARSER (RequirementItem creation)")
print("="*50)
from dataclasses import replace
settings = replace(
    Settings.from_env(),
    openai_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"),
    openai_model=os.getenv("LLM_MODEL") or "gemini-2.5-flash",
)
parse_res = parse_requirements_from_email(
    subject=subject,
    body=raw_body,
    settings=settings,
    from_email=from_email
)
print(f"Parsed requirements count: {len(parse_res.requirements)}")
parsed_item = parse_res.requirements[0] if parse_res.requirements else None
if parsed_item:
    print("Parsed item fields:")
    for k, v in parsed_item.model_dump().items():
        if k in ['job_title', 'location', 'experience_text', 'experience_min_years', 'experience_max_years',
                 'budget_text', 'monthly_budget', 'yearly_budget_min', 'yearly_budget_max',
                 'mandatory_skills', 'soft_skills', 'notice_period', 'work_mode_text', 'work_mode',
                 'number_of_positions', 'req_id', 'field_evidence_quotes']:
            print(f"  {k}: {repr(v)}")

print("\n" + "="*50)
print("STAGE 7: FIELD_MAPPER (map_to_metaforge)")
print("="*50)
if parsed_item:
    from field_mapper import EmailContext
    ctx = EmailContext(
        graph_message_id=payload.get("graphMessageId", ""),
        internet_message_id=payload.get("internetMessageId", ""),
        to_emails=payload.get("to", ""),
        cc_emails=payload.get("cc", ""),
        from_email=from_email,
        from_name=from_email,
    )
    from datetime import date
    mapped_payload = map_to_metaforge(
        parsed_item.model_dump(mode="json", by_alias=True),
        ctx=ctx,
        client_display_name=client_name,
        job_id="2026/10/05-011",
        client_jd_id=parsed_item.req_id,
        body_text=cleaned_b_text,
        internal_poc_default="offshore demands",
        jd_count=1,
        demand_received_date=date(2026, 10, 5),
        email_subject=subject,
        email_body_plain=raw_body,
        email_body_html=raw_html,
        email_received_iso=payload.get("receivedDateTime", ""),
    )
    target_fields = [
        'number_of_positions', 'overall_experience', 'work_mode',
        'mandatory_skills', 'skills', 'monthly_budget', 'yearly_budget', 'notice_period',
        'location', 'job_title'
    ]
    for tf in target_fields:
        print(f"  mapped {tf}: {repr(mapped_payload.get(tf))}")

print("\n" + "="*50)
print("\n" + "="*50)
print("STAGE 8: HISTORICAL AUTOFILL & TWO-WAY VERIFIER")
print("="*50)
print(f"is_strict_field_mapping(): {is_strict_field_mapping()}")
print("In main.py: historical autofill is skipped when is_strict_field_mapping() is True.")

print("\n" + "="*50)
print("STAGE 9: VALIDATOR (validate_requirement_before_save)")
print("="*50)
val_payload, should_route, reason = validate_requirement_before_save(
    dict(mapped_payload),
    block_text=cleaned_b_text,
    client=client_name,
)
print(f"should_route_review: {should_route}, reason: {reason}")
for tf in target_fields:
    print(f"  validated {tf}: {repr(val_payload.get(tf))}")


print("\n" + "="*50)
print("STAGE 10: STORED DB PAYLOAD (CURRENT IN DB)")
print("="*50)
for tf in target_fields:
    print(f"  db_payload {tf}: {repr(payload.get(tf))}")

print("\n" + "="*50)
print("STAGE 11: UI PROJECTION (get_requirement)")
print("="*50)
for tf in target_fields:
    print(f"  ui {tf}: {repr(rec.get(tf) or payload.get(tf))}")



