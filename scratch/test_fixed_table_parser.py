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

def parse_html_tables_key_value_fixed(body_html: str, display_name: str = "Accenture") -> list[RequirementItem]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    tables = soup.find_all("table")
    items: list[RequirementItem] = []
    seen_ids: set[str] = set()
    
    current_item: RequirementItem | None = None
    
    for tbl in tables:
        trs = tbl.find_all("tr")
        if not trs:
            continue
            
        table_req_id = None
        
        # Check if table itself contains a Request-ID row or Summary row
        for tr in trs:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
            if not cells or not any(cells):
                continue
                
            first_cell = cells[0].strip()
            # Summary matrix row
            if re.match(r"^(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d|RQ\d{5,8}|DLTJP\d{5,10})$", first_cell, re.IGNORECASE):
                req_id = first_cell
                if req_id not in seen_ids:
                    seen_ids.add(req_id)
                    title_val = cells[2] if len(cells) > 2 else ""
                    loc_val = cells[3] if len(cells) > 3 else ""
                    exp_val = cells[6] if len(cells) > 6 else ""
                    stat_val = cells[8] if len(cells) > 8 else (cells[-1] if len(cells) > 1 else "open")
                    norm_stat = "hold" if "hold" in stat_val.lower() else ("open" if stat_val.lower() in ("open", "p1", "p2") else stat_val)
                    
                    current_item = RequirementItem(
                        req_id=req_id,
                        raw_status=stat_val,
                        job_title=title_val or f"{display_name} Requirement",
                        location=[loc_val] if loc_val else [],
                        experience=exp_val,
                        priority="HIGH" if norm_stat == "open" else "LOW",
                        client_name=display_name,
                        mandatory_skills=[title_val] if title_val else [],
                        confidence=1.0,
                    )
                    items.append(current_item)
                    table_req_id = req_id
                break
                
            # Key-value row
            if len(cells) >= 2:
                key = cells[0].strip().rstrip(":").lower()
                val = cells[1].strip()
                if key in ("request-id", "request id", "req id", "req-id", "reqid", "so id", "demand id"):
                    m = re.search(r"(\d{5,7}-\d{1,2}|20\d{5}-\d|19\d{5}-\d|17\d{5}-\d|RQ\d{5,8}|DLTJP\d{5,10})", val, re.IGNORECASE)
                    if m:
                        req_id = m.group(1)
                        if req_id not in seen_ids:
                            seen_ids.add(req_id)
                            is_hold_body = "don't work" in body_html.lower() or "dont work" in body_html.lower()
                            raw_stat = "hold" if is_hold_body else "open"
                            current_item = RequirementItem(
                                req_id=req_id,
                                raw_status=raw_stat,
                                job_title=f"{display_name} Requirement",
                                priority="HIGH" if raw_stat == "open" else "LOW",
                                client_name=display_name,
                                confidence=1.0,
                            )
                            items.append(current_item)
                            table_req_id = req_id
                        elif current_item and current_item.req_id == req_id:
                            table_req_id = req_id
                        break
                        
        # If this table didn't have a Request-ID row, process its key-value fields for current_item
        if not table_req_id and current_item:
            for tr in trs:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["th", "td"])]
                if len(cells) >= 2:
                    key = cells[0].strip().rstrip(":").lower()
                    val = cells[1].strip()
                    
                    if key in ("job description", "jd", "job summary"):
                        if "Summary:" in val:
                            summary_part = val.split("Summary:", 1)[1]
                            m_title = re.search(r"As a ([^,]+?),(?:\s*a typical day|\s*you will|\s*the)", summary_part, re.IGNORECASE)
                            if m_title:
                                extracted_title = m_title.group(1).strip()
                                current_item.job_title = extracted_title
                                if not current_item.mandatory_skills:
                                    current_item.mandatory_skills = [extracted_title]
                        m_skill = re.search(r"Must To Have Skills:\s*([^.\n]+)", val, re.IGNORECASE)
                        if m_skill:
                            skill = m_skill.group(1).strip()
                            current_item.mandatory_skills = [skill]
                            if current_item.job_title == f"{display_name} Requirement":
                                current_item.job_title = skill
                                
                    elif key in ("comments for suppliers", "comments", "supplier comments"):
                        if current_item.job_title == f"{display_name} Requirement":
                            m_comp = re.search(r"^([A-Za-z0-9\s/&\-\(\)]+?)(?:Relevant|Work|Location|\d+\+|\d+ Yrs|$)", val, re.IGNORECASE)
                            if m_comp and len(m_comp.group(1).strip()) > 3:
                                current_item.job_title = m_comp.group(1).strip()

    return items

extracted = parse_html_tables_key_value_fixed(body)
print(f"Extracted count with fixed table parser: {len(extracted)}")
for idx, r in enumerate(extracted):
    print(f"Item #{idx+1:2d}: req_id={r.req_id:<12} | title={r.job_title:<45} | status={r.raw_status}")
