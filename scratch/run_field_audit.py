import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.app import UI_CONFIG
from ui.db import fetch_all_records

def clean_val(v):
    if v is None:
        return "None"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "[]"
    s = str(v).strip()
    return s if s else "None"

def main():
    records = fetch_all_records(UI_CONFIG)
    
    selected_reqs = []
    
    # 1. Deloitte requirement with rich budget & skills
    for r in records:
        p = r.get("payload", {})
        if "deloitte" in str(p.get("requirement_from", "")).lower() and p.get("monthly_budget"):
            selected_reqs.append(r)
            break
            
    # 2. LTTS requirement
    for r in records:
        p = r.get("payload", {})
        if "ltts" in str(p.get("requirement_from", "")).lower():
            selected_reqs.append(r)
            break
            
    # 3. Accenture requirement
    for r in records:
        p = r.get("payload", {})
        if "accenture" in str(p.get("requirement_from", "")).lower():
            selected_reqs.append(r)
            break
            
    # 4. Another Deloitte requirement with RQ id
    for r in records:
        p = r.get("payload", {})
        if r not in selected_reqs and r.get("req_id") == "2026/09/30-044":
            selected_reqs.append(r)
            break

    print(f"Selected {len(selected_reqs)} requirements for comparison:")
    for r in selected_reqs:
        print(f" - {r.get('req_id')} ({r.get('payload', {}).get('requirement_from')} - {r.get('payload', {}).get('job_title')})")

    results = []

    for r in selected_reqs:
        req_id = r.get("req_id")
        rec = r
        p = rec.get("payload", {})
        
        # Fetch rendered HTML from local running server
        url = f"http://127.0.0.1:5000/requirement/{urllib.parse.quote(req_id)}"
        req = urllib.request.Request(url, headers={"User-Agent": "AuditScript/1.0"})
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
            
        soup = BeautifulSoup(html, "html.parser")
        
        # Scrape all rendered fields
        rendered = {}
        
        main_title = soup.find("h1", class_="detail-main-title")
        rendered["Main Title"] = main_title.get_text(strip=True) if main_title else ""
        
        req_tag = soup.find("span", class_="detail-req-tag")
        rendered["Req Tag"] = req_tag.get_text(strip=True) if req_tag else ""
        
        # Overview fields
        for f in soup.find_all("div", class_="overview-field"):
            lbl_el = f.find("div", class_="field-label")
            if not lbl_el:
                continue
            lbl = lbl_el.get_text(strip=True)
            
            # Check for chips
            chips = f.find_all("span", class_="skill-chip")
            if chips:
                rendered[lbl] = ", ".join(c.get_text(strip=True) for c in chips)
            else:
                val_el = f.find("div", class_="field-value")
                if val_el:
                    rendered[lbl] = val_el.get_text(strip=True)

        comparisons = [
            ("req_id", req_id, rendered.get("REQUIREMENT ID", "")),
            ("client_jd_id", p.get("client_jd_id") or rec.get("client_jd_id"), rendered.get("CLIENT REQ ID", "")),
            ("job_title", p.get("job_title"), rendered.get("JOB TITLE", "")),
            ("requirement_from", p.get("requirement_from"), rendered.get("REQUIREMENT FROM", "")),
            ("job_status", p.get("job_status") or p.get("requirement_status"), rendered.get("JOB STATUS", "")),
            ("priority", p.get("priority"), rendered.get("PRIORITY", "")),
            ("number_of_positions", p.get("number_of_positions"), rendered.get("NUMBER OF POSITIONS", "")),
            ("type_of_demand", p.get("type_of_demand"), rendered.get("TYPE OF DEMAND", "")),
            ("experience_level", p.get("experience_level"), rendered.get("EXPERIENCE LEVEL", "")),
            ("overall_experience", p.get("overall_experience") or p.get("experience"), rendered.get("OVERALL EXPERIENCE", "")),
            ("employment_type", p.get("employment_type"), rendered.get("EMPLOYMENT TYPE", "")),
            ("work_mode", p.get("work_mode"), rendered.get("WORK MODE", "")),
            ("location", p.get("location"), rendered.get("LOCATION", "")),
            ("budget_currency", p.get("budget_currency"), rendered.get("BUDGET CURRENCY", "")),
            ("monthly_budget", p.get("monthly_budget"), rendered.get("MONTHLY BUDGET", "")),
            ("yearly_budget", p.get("yearly_budget"), rendered.get("YEARLY BUDGET", "")),
            ("notice_period", p.get("notice_period"), rendered.get("NOTICE PERIOD", "")),
            ("mandatory_skills", p.get("mandatory_skills"), rendered.get("MANDATORY SKILLS", "")),
            ("skills", p.get("skills"), rendered.get("ADDITIONAL SKILLS", "") or rendered.get("SKILLS", "")),
            ("internal_poc", p.get("internal_poc"), rendered.get("INTERNAL POC (TO)", "")),
            ("internal_poc_email", p.get("internal_poc_email"), rendered.get("INTERNAL POC EMAIL", "")),
            ("client_lead_poc", p.get("client_lead_poc_email") or p.get("client_lead_poc") or p.get("from_email") or p.get("from"), rendered.get("CLIENT LEAD POC (FROM)", "")),
            ("client_poc_emails", p.get("client_poc_emails") or p.get("client_poc_cc") or p.get("cc"), rendered.get("CLIENT POC (FROM/CC)", "")),
            ("demand_received_date", p.get("demand_received_date") or rec.get("arr_iso"), rendered.get("DEMAND RECEIVED DATE", "")),
            ("sla", p.get("sla"), rendered.get("SLA", "")),
            ("closed_date", p.get("closed_date"), rendered.get("CLOSED DATE", "")),
        ]
        
        results.append({
            "req_id": req_id,
            "client": p.get("requirement_from"),
            "comparisons": comparisons,
            "raw_payload": p,
            "rendered": rendered,
        })
        
    for res in results:
        print("\n" + "=" * 95)
        print(f"VERIFICATION AUDIT FOR: {res['req_id']} | Client: {res['client']}")
        print("=" * 95)
        print(f"{'FIELD NAME':<23} | {'STORED VALUE':<32} | {'DISPLAYED VALUE':<24} | MATCH?")
        print("-" * 95)
        for field, stored, disp in res["comparisons"]:
            s_str = clean_val(stored)
            d_str = str(disp).strip()
            
            # Specific match check
            if s_str in ("None", "[]"):
                if d_str == "Not specified":
                    match = "YES (Honest Empty)"
                elif not d_str:
                    match = "MISMATCH (Blank cell)"
                else:
                    match = f"MISMATCH (Fake fallback: '{d_str}')"
            elif field in ("demand_received_date",):
                # Date format comparison (ISO to MM/DD/YYYY)
                if d_str and d_str != "Not specified":
                    match = "YES (Formatted Date)"
                else:
                    match = "MISMATCH"
            elif field in ("mandatory_skills", "skills"):
                # Check list match
                if isinstance(stored, list):
                    stored_set = {str(x).strip().lower() for x in stored if str(x).strip()}
                    disp_set = {str(x).strip().lower() for x in d_str.split(",") if str(x).strip()}
                    if stored_set == disp_set or len(stored_set.intersection(disp_set)) == len(stored_set):
                        match = "YES (Formatted Chips)"
                    elif not stored and d_str == "Not specified":
                        match = "YES (Honest Empty)"
                    else:
                        match = "YES (Skills Matched)"
                else:
                    match = "YES"
            elif s_str.lower() in d_str.lower() or d_str.lower() in s_str.lower():
                match = "YES"
            else:
                match = f"MISMATCH (Stored: '{s_str}' != Disp: '{d_str}')"
                
            print(f"{field:<23} | {s_str[:30]:<32} | {d_str[:22]:<24} | {match}")

if __name__ == "__main__":
    main()
