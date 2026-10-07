import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from ui.db import get_requirement
from ui.app import format_received_time, format_open_since, UI_CONFIG

rec = get_requirement(UI_CONFIG, '2026/09/30-044')
if not rec:
    print("Record not found for 2026/09/30-044!")
    # Try with RQ056293
    rec = get_requirement(UI_CONFIG, 'RQ056293')

if rec:
    p = rec.get('payload', {})
    print("SUCCESS: Found requirement!")
    print(f"Req ID: {rec.get('req_id')}")
    print(f"Client JD ID: {rec.get('client_jd_id')}")
    print(f"Job Status: {rec.get('job_status')}")
    print(f"Job Title: {p.get('job_title')}")
    print(f"Client: {p.get('requirement_from')}")
    print(f"Internal POC Email: {p.get('internal_poc_email') or p.get('to')}")
    print(f"Client Lead POC: {p.get('client_lead_poc')}")
    print(f"Monthly Budget: {p.get('monthly_budget')}")
    print(f"Budget Currency: {p.get('budget_currency')}")
    print(f"Notice Period: {p.get('notice_period')}")
    print(f"Skills: {p.get('skills')}")
    
    r_date = p.get('receivedDateTime') or p.get('received_date_time') or p.get('email_received_iso') or rec.get('arr_iso') or rec.get('created_at') or p.get('demand_received_date')
    print(f"Raw Arrival Date: {r_date}")
    formatted_time = format_received_time(r_date)
    print(f"Formatted Arrival Time on UI: {formatted_time}")
    print(f"Formatted Open Since on UI: {format_open_since(r_date)}")
else:
    print("Record could not be retrieved.")
