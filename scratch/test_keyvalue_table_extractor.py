import json
import sys
import os
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))
from models import RequirementItem, Priority

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

body_obj = msg.get('body', {}) or {}
body = body_obj.get('content', '')

def parse_html_tables_key_value(body_html: str, display_name: str = "Accenture") -> list[RequirementItem]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    tables = soup.find_all("table")
    items: list[RequirementItem] = []
    
    current_req = None
    
    for tbl_idx, tbl in enumerate(tables):
        trs = tbl.find_all("tr")
        for tr in trs:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
            if not cells or not any(cells):
                continue
                
            # Check 1: Summary matrix row where cell 0 is a Req ID (e.g. 209160-1)
            first_cell = cells[0].strip()
            if re.match(r"^(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d|RQ\d{5,8}|DLTJP\d{5,10})$", first_cell, re.IGNORECASE):
                req_id = first_cell
                title_val = cells[2] if len(cells) > 2 else ""
                loc_val = cells[3] if len(cells) > 3 else ""
                exp_val = cells[6] if len(cells) > 6 else ""
                stat_val = cells[8] if len(cells) > 8 else (cells[-1] if len(cells) > 1 else "open")
                
                # Check if we already created current_req for this req_id or if new
                current_req = RequirementItem(
                    req_id=req_id,
                    raw_status=stat_val,
                    job_title=title_val or f"{display_name} Requirement",
                    location=[loc_val] if loc_val else [],
                    experience=exp_val,
                    priority=Priority.HIGH if stat_val.lower() in ("p1", "p2", "open") else Priority.LOW,
                    client_name=display_name,
                    mandatory_skills=[title_val] if title_val else [],
                    confidence=1.0,
                )
                items.append(current_req)
                continue
            
            # Check 2: Key-Value row format
            if len(cells) >= 2:
                key = cells[0].strip().rstrip(":").lower()
                val = cells[1].strip()
                
                if key in ("request-id", "request id", "req id", "req-id", "reqid", "so id", "demand id"):
                    # Extract req ID if not already matched
                    if val and re.search(r"(\d{5,7}-\d{1,2}|20\d{5}-\d|RQ\d{5,8}|DLTJP\d+)", val, re.IGNORECASE):
                        m = re.search(r"(\d{5,7}-\d{1,2}|20\d{5}-\d|RQ\d{5,8}|DLTJP\d+)", val, re.IGNORECASE)
                        req_id = m.group(1)
                        
                        # Check if current_req is the same req_id
                        if current_req and current_req.req_id == req_id:
                            pass # already added
                        else:
                            current_req = RequirementItem(
                                req_id=req_id,
                                raw_status="open",
                                job_title=f"{display_name} Requirement",
                                priority=Priority.HIGH,
                                client_name=display_name,
                                confidence=1.0,
                            )
                            items.append(current_req)
                            
                elif key in ("job description", "jd", "job summary") and current_req:
                    # Extract title / skills from Job Description if job_title is default
                    if "Summary:" in val:
                        summary_part = val.split("Summary:", 1)[1]
                        # E.g. "As a Custom Software Engineer, a typical day..."
                        m_title = re.search(r"As a ([^,]+?),(?:\s*a typical day|\s*you will|\s*the)", summary_part, re.IGNORECASE)
                        if m_title:
                            extracted_title = m_title.group(1).strip()
                            current_req.job_title = extracted_title
                            if not current_req.mandatory_skills:
                                current_req.mandatory_skills = [extracted_title]
                                
                    m_skill = re.search(r"Must To Have Skills:\s*([^.\n]+)", val, re.IGNORECASE)
                    if m_skill and current_req:
                        skill = m_skill.group(1).strip()
                        current_req.mandatory_skills = [skill]
                        if current_req.job_title == f"{display_name} Requirement":
                            current_req.job_title = skill
                            
                elif key in ("comments for suppliers", "comments", "supplier comments") and current_req:
                    if current_req.job_title == f"{display_name} Requirement":
                        # Try extracting title from comments for suppliers
                        # E.g. "SAP FSCM Treasury and Risk Management (TRM)Relevant exp 8 Yrs"
                        m_comp = re.search(r"^([A-Za-z0-9\s/&\-\(\)]+?)(?:Relevant|Work|Location|\d+\+|\d+ Yrs|$)", val, re.IGNORECASE)
                        if m_comp and len(m_comp.group(1).strip()) > 3:
                            current_req.job_title = m_comp.group(1).strip()

    return items

extracted = parse_html_tables_key_value(body)
print(f"Extracted key-value table items: {len(extracted)}")
for idx, r in enumerate(extracted):
    print(f"Item #{idx+1:2d}: req_id={r.req_id:<15} | title={r.job_title:<45} | status={r.raw_status}")
