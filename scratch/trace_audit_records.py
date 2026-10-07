import sqlite3
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()

test_ids = ['2026/09/07-023', '2026/09/08-005', '2026/09/30-007', '2026/09/11-159', '2026/09/29-024']

print("=== DETAILED TRACE ON HISTORICAL RECORDS ===")
for jid in test_ids:
    c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE job_id = ? OR former_job_id = ? LIMIT 1", (jid, jid))
    row = c.fetchone()
    if not row:
        # try searching in payload_json
        c.execute("SELECT job_id, client_jd_id, payload_json FROM metaforge_requirements WHERE payload_json LIKE ? LIMIT 1", (f'%{jid}%',))
        row = c.fetchone()
    if not row:
        print(f"\n[NOT FOUND] Job ID: {jid}")
        continue
    job_id, cjd, p_json = row
    p = json.loads(p_json)
    body = p.get('bodyText') or ''
    subj = p.get('subject') or ''
    print(f"\n=======================================================")
    print(f"JOB ID: {job_id} | Client ID: {cjd} | Client: {p.get('requirement_from')}")
    print(f"Subject: {subj}")
    print(f"Body Length: {len(body)} chars")
    
    # Check what appears in body text
    print("\n--- Raw Body Excerpts ---")
    for keyword in ["skill", "exp", "location", "bangalore", "pune", "chennai", "vadodara", "hyderabad", "budget", "rate", "lpm", "lpa", "positions", "notice", "hybrid", "remote", "onsite", "office"]:
        matches = [m.start() for m in re.finditer(re.escape(keyword), body, re.IGNORECASE)]
        if matches:
            first_m = matches[0]
            snippet = body[max(0, first_m-40):min(len(body), first_m+80)].replace('\n', ' ')
            print(f"  [{keyword.upper()} @ char {first_m}]: {snippet}")

    print("\n--- Stored DB Values in payload_json ---")
    print(f"  job_title           : {p.get('job_title')}")
    print(f"  location            : {p.get('location')}")
    print(f"  mandatory_skills    : {p.get('mandatory_skills')}")
    print(f"  skills              : {p.get('skills')}")
    print(f"  overall_experience  : {p.get('overall_experience')} (min={p.get('overall_experience_min')}, max={p.get('overall_experience_max')})")
    print(f"  work_mode           : {p.get('work_mode')} (text={p.get('work_mode_text')})")
    print(f"  number_of_positions : {p.get('number_of_positions')}")
    print(f"  notice_period       : {p.get('notice_period')}")
    print(f"  budget_text         : {p.get('budget_text')} / budget={p.get('budget')}")
    print(f"  monthly_budget      : {p.get('monthly_budget')} (min={p.get('monthly_budget_min')}, max={p.get('monthly_budget_max')})")
    print(f"  yearly_budget       : {p.get('yearly_budget')} (min={p.get('yearly_budget_min')}, max={p.get('yearly_budget_max')})")
    print(f"  internal_poc        : {p.get('internal_poc')}")
    print(f"  client_poc          : {p.get('client_poc')}")
