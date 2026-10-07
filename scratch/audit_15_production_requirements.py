import sqlite3
import json
import os
import sys
import re
from datetime import date
from dotenv import load_dotenv

load_dotenv('Auto_email_extraction/.env')
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Auto_email_extraction'))

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
from boilerplate_learner import clean_structure_and_extract_boilerplate
from client_detector import detect_client
from field_mapper import map_to_metaforge, EmailContext
from strict_validator import validate_requirement_before_save

TARGET_REQS = [
    '2026/10/05-011',
    '2026/10/05-010',
    '2026/10/05-009',
    '2026/10/05-008',
    '2026/10/05-007',
    '2026/09/30-006',
    '2026/09/30-007',
    '2026/09/30-008',
    '2026/09/08-004',
    '2026/09/08-005',
    '2026/09/17-004',
    '2026/09/07-013',
    '2026/09/07-023',
    '2026/09/21-002',
    '2026/09/29-024',
]

TARGET_FIELDS = [
    'job_title',
    'location',
    'mandatory_skills',
    'additional_skills',
    'experience',
    'number_of_positions',
    'notice_period',
    'work_mode',
    'monthly_budget',
    'yearly_budget',
    'tiered_budget',
    'employment_type',
    'client_jd_id',
]

def run_trace():
    results = {}
    con = sqlite3.connect('Auto_email_extraction/data/metaforge_requirements.db')
    cur = con.cursor()

    for req_id in TARGET_REQS:
        print(f"Tracing {req_id}...")
        row = cur.execute('SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ? OR client_jd_id = ?', (req_id, req_id)).fetchone()
        if not row:
            print(f"Missing {req_id}")
            continue

        db_job_id, db_client_jd_id, payload_json = row
        db_payload = json.loads(payload_json)

        # 1. Source
        source_body = db_payload.get('bodyText', '')
        source_subj = db_payload.get('subject', '')
        from_email = db_payload.get('from', '') or db_payload.get('client_lead_poc', '') or ''
        client_name = db_payload.get('requirement_from', '')

        # UI view
        ui_rec = get_requirement(UI_CONFIG, db_job_id) or {"payload": db_payload}
        ui_payload = ui_rec.get("payload", {})

        # 2. Preprocess
        seg = _latest_thread_segment(source_body)
        cleaned_no_tables = _strip_candidate_tables(seg)
        cleaned_b_text, removed_lines = clean_structure_and_extract_boilerplate(cleaned_no_tables, client=client_name)

        # 3. LLM prompt text
        prompt_text = cleaned_b_text[:2500]

        # 4. LLM output (run live parser if API key available)
        settings = Settings.from_env()
        parsed_res = None
        try:
            parsed_res = parse_requirements_from_email(
                subject=source_subj,
                body=source_body,
                settings=settings,
                from_email=from_email
            )
        except Exception as e:
            print(f"Parser call error for {req_id}: {e}")

        parsed_item = None
        if parsed_res and parsed_res.requirements:
            # find matching requirement if multi-req email
            if db_client_jd_id:
                for r in parsed_res.requirements:
                    if r.req_id == db_client_jd_id:
                        parsed_item = r
                        break
            if not parsed_item:
                parsed_item = parsed_res.requirements[0]

        # 5. Mapper
        mapped = {}
        if parsed_item:
            ctx = EmailContext(
                graph_message_id=db_payload.get("graphMessageId", ""),
                internet_message_id=db_payload.get("internetMessageId", ""),
                to_emails=db_payload.get("to", ""),
                cc_emails=db_payload.get("cc", ""),
                from_email=from_email,
                from_name=from_email,
            )
            mapped = map_to_metaforge(
                parsed_item.model_dump(mode="json", by_alias=True),
                ctx=ctx,
                client_display_name=client_name,
                job_id=db_job_id,
                client_jd_id=db_client_jd_id,
                body_text=cleaned_b_text,
                internal_poc_default="offshore demands",
                jd_count=len(parsed_res.requirements),
                demand_received_date=date.today(),
                email_subject=source_subj,
                email_body_plain=source_body,
                email_received_iso=db_payload.get("email_received_iso", ""),
            )

        # 6. Validator
        validated = {}
        if mapped:
            validated, _, _ = validate_requirement_before_save(
                mapped,
                block_text=cleaned_b_text,
                client=client_name
            )

        results[req_id] = {
            "source_subj": source_subj,
            "source_body_len": len(source_body),
            "client": client_name,
            "cjd": db_client_jd_id,
            "source_text_snippet": source_body[:1500],
            "parsed_item": parsed_item.model_dump(mode="json") if parsed_item else None,
            "mapped": mapped,
            "validated": validated,
            "db": db_payload,
            "ui": ui_payload
        }

    with open('Auto_email_extraction/scratch/audit_results_15.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("Trace completed. Results saved to Auto_email_extraction/scratch/audit_results_15.json")

if __name__ == '__main__':
    run_trace()
