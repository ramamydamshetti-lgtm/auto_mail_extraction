import sqlite3
import json
import re
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

def parse_accenture_table_rows(html_body, text_body=""):
    items = []
    if not html_body:
        return items
    soup = BeautifulSoup(html_body, 'html.parser')
    tables = soup.find_all('table')
    if not tables:
        return items
        
    for tbl in tables:
        trs = tbl.find_all('tr')
        if not trs:
            continue
        
        # Check header
        headers = [td.get_text(strip=True) for td in trs[0].find_all(['th', 'td'])]
        req_id_idx = None
        status_idx = None
        title_idx = None
        loc_idx = None
        exp_idx = None
        budget_idx = None
        
        for idx, h in enumerate(headers):
            hl = h.lower()
            if 'req' in hl and 'id' in hl:
                req_id_idx = idx
            elif 'priority' in hl or 'status' in hl:
                status_idx = idx
            elif 'skill' in hl or 'role' in hl or 'title' in hl:
                title_idx = idx
            elif 'location' in hl:
                loc_idx = idx
            elif 'exp' in hl:
                exp_idx = idx
            elif 'budget' in hl:
                budget_idx = idx
                
        if req_id_idx is not None:
            # Header table
            for tr in trs[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td'])]
                if len(cells) == len(headers) and cells[req_id_idx]:
                    req_id = cells[req_id_idx].strip()
                    if req_id and req_id.lower() not in ('request-id', 'req id', 'so id'):
                        status_val = cells[status_idx] if status_idx is not None else cells[-1]
                        title_val = cells[title_idx] if title_idx is not None else ''
                        loc_val = cells[loc_idx] if loc_idx is not None else ''
                        exp_val = cells[exp_idx] if exp_idx is not None else ''
                        budget_val = cells[budget_idx] if budget_idx is not None else ''
                        
                        items.append({
                            'req_id': req_id,
                            'job_title': title_val,
                            'location': [loc_val] if loc_val else [],
                            'experience': exp_val,
                            'budget': budget_val,
                            'raw_status': status_val,
                            'mandatory_skills': [title_val] if title_val else []
                        })
        else:
            # Single row reply table without header row
            first_cells = [td.get_text(strip=True) for td in trs[0].find_all(['td'])]
            if first_cells and re.match(r'^\d{5,8}(-\d+)?$', first_cells[0]):
                req_id = first_cells[0].strip()
                status_val = first_cells[-1]
                title_val = first_cells[2] if len(first_cells) > 2 else ''
                loc_val = first_cells[3] if len(first_cells) > 3 else ''
                exp_val = first_cells[6] if len(first_cells) > 6 else ''
                budget_val = first_cells[5] if len(first_cells) > 5 else ''
                
                items.append({
                    'req_id': req_id,
                    'job_title': title_val,
                    'location': [loc_val] if loc_val else [],
                    'experience': exp_val,
                    'budget': budget_val,
                    'raw_status': status_val,
                    'mandatory_skills': [title_val] if title_val else []
                })
                
    return items

def run_test():
    conn = sqlite3.connect('data/processed_messages.db')
    cur = conn.cursor()
    rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()
    conn.close()
    
    total_parsed_items = 0
    distinct_gids = set()
    
    for r in rows:
        p = json.loads(r[0])
        gid = p.get('graphMessageId') or p.get('internetMessageId')
        html = p.get('bodyHtml')
        if gid not in distinct_gids and html:
            distinct_gids.add(gid)
            extracted = parse_accenture_table_rows(html)
            total_parsed_items += len(extracted)
            if extracted:
                print(f"Subj: {p.get('subject')[:40]} | Extracted {len(extracted)} items (e.g. ReqID={extracted[0]['req_id']}, Status={extracted[0]['raw_status']}, Title={extracted[0]['job_title']})")
                
    print(f"\nTotal distinct emails tested: {len(distinct_gids)}")
    print(f"Total requirement items extracted via table parser: {total_parsed_items}")

if __name__ == '__main__':
    run_test()
