import json
import os
import sys

with open('Auto_email_extraction/scratch/audit_results_15.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Loaded audit data for {len(data)} requirements.")

FIELDS = [
    'job_title',
    'location',
    'mandatory_skills',
    'skills',  # additional_skills
    'experience',
    'number_of_positions',
    'notice_period',
    'work_mode',
    'monthly_budget',
    'yearly_budget',
    'tiered_budget',
    'employment_type',
    'client_jd_id'
]

summary_by_field = {f: {"source_present": 0, "llm_captured": 0, "parsed": 0, "mapped": 0, "validated": 0, "in_db": 0, "in_ui": 0, "issues": []} for f in FIELDS}

for req_id, rec in data.items():
    source_snippet = rec.get("source_text_snippet", "")
    parsed = rec.get("parsed_item") or {}
    mapped = rec.get("mapped") or {}
    validated = rec.get("validated") or {}
    db = rec.get("db") or {}
    ui = rec.get("ui") or {}

    print(f"\n=======================================================")
    print(f"REQ: {req_id} | Client: {rec.get('client')} | CJD: {rec.get('cjd')}")
    print(f"Job Title in DB: {db.get('job_title')}")
    print(f"=======================================================")

    # 1. job_title
    print(f"  [job_title]")
    print(f"    LLM: {parsed.get('job_title')}")
    print(f"    Map: {mapped.get('job_title')}")
    print(f"    Val: {validated.get('job_title')}")
    print(f"    DB : {db.get('job_title')}")
    print(f"    UI : {ui.get('job_title')}")

    # 2. location
    print(f"  [location]")
    print(f"    LLM: {parsed.get('location')}")
    print(f"    Map: {mapped.get('location')}")
    print(f"    Val: {validated.get('location')}")
    print(f"    DB : {db.get('location')}")
    print(f"    UI : {ui.get('location')}")

    # 3. mandatory_skills
    print(f"  [mandatory_skills]")
    print(f"    LLM: {parsed.get('mandatory_skills')}")
    print(f"    Map: {mapped.get('mandatory_skills')}")
    print(f"    Val: {validated.get('mandatory_skills')}")
    print(f"    DB : {db.get('mandatory_skills')}")
    print(f"    UI : {ui.get('mandatory_skills')}")

    # 4. skills (additional_skills)
    print(f"  [skills / additional_skills]")
    print(f"    LLM: {parsed.get('soft_skills')}")
    print(f"    Map: {mapped.get('skills')}")
    print(f"    Val: {validated.get('skills')}")
    print(f"    DB : {db.get('skills')}")
    print(f"    UI : {ui.get('skills')}")

    # 5. experience
    print(f"  [experience]")
    print(f"    LLM: text={parsed.get('experience_text')} min={parsed.get('experience_min_years')} max={parsed.get('experience_max_years')}")
    print(f"    Map: {mapped.get('overall_experience')} (min={mapped.get('overall_experience_min')}, max={mapped.get('overall_experience_max')})")
    print(f"    Val: {validated.get('overall_experience')}")
    print(f"    DB : {db.get('overall_experience')}")
    print(f"    UI : {ui.get('overall_experience') or ui.get('experience')}")

    # 6. number_of_positions
    print(f"  [number_of_positions]")
    print(f"    LLM: {parsed.get('number_of_positions')}")
    print(f"    Map: {mapped.get('number_of_positions')}")
    print(f"    Val: {validated.get('number_of_positions')}")
    print(f"    DB : {db.get('number_of_positions')}")
    print(f"    UI : {ui.get('number_of_positions')}")

    # 7. notice_period
    print(f"  [notice_period]")
    print(f"    LLM: {parsed.get('notice_period')}")
    print(f"    Map: {mapped.get('notice_period')}")
    print(f"    Val: {validated.get('notice_period')}")
    print(f"    DB : {db.get('notice_period')}")
    print(f"    UI : {ui.get('notice_period')}")

    # 8. work_mode
    print(f"  [work_mode]")
    print(f"    LLM: text={parsed.get('work_mode_text')} val={parsed.get('work_mode')}")
    print(f"    Map: {mapped.get('work_mode')}")
    print(f"    Val: {validated.get('work_mode')}")
    print(f"    DB : {db.get('work_mode')}")
    print(f"    UI : {ui.get('work_mode')}")

    # 9. budget (monthly, yearly, tiered)
    print(f"  [budget]")
    print(f"    LLM: text={parsed.get('budget_text')} monthly={parsed.get('monthly_budget')} yearly_min={parsed.get('yearly_budget_min')} yearly_max={parsed.get('yearly_budget_max')}")
    print(f"    Map: monthly={mapped.get('monthly_budget')} yearly={mapped.get('yearly_budget')} text={mapped.get('budget_text')}")
    print(f"    Val: monthly={validated.get('monthly_budget')} yearly={validated.get('yearly_budget')}")
    print(f"    DB : monthly={db.get('monthly_budget')} yearly={db.get('yearly_budget')}")
    print(f"    UI : monthly={ui.get('monthly_budget')} yearly={ui.get('yearly_budget')}")

    # 10. employment_type
    print(f"  [employment_type]")
    print(f"    LLM: {parsed.get('employment_type')}")
    print(f"    Map: {mapped.get('employment_type')}")
    print(f"    Val: {validated.get('employment_type')}")
    print(f"    DB : {db.get('employment_type')}")
    print(f"    UI : {ui.get('employment_type')}")

    # 11. client_jd_id
    print(f"  [client_jd_id]")
    print(f"    LLM: {parsed.get('req_id') or parsed.get('client_jd_id')}")
    print(f"    Map: {mapped.get('client_jd_id')}")
    print(f"    Val: {validated.get('client_jd_id')}")
    print(f"    DB : {db.get('client_jd_id')}")
    print(f"    UI : {ui.get('client_jd_id')}")
