import sqlite3
import json
import csv
import sys
import os
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

def run_analysis():
    print("=== ACCENTURE REQUIREMENTS ANALYSIS & DRY RUN ===")
    
    # Collect all Accenture emails from DB (pending_reviews + filtered_log) and latest_500_all.csv
    accenture_emails = [] # list of dict: {gid, date, subject, from, html, text}
    seen_gids = set()
    
    # 1. From processed_messages.db
    if os.path.exists('data/processed_messages.db'):
        conn = sqlite3.connect('data/processed_messages.db')
        cur = conn.cursor()
        
        # pending_reviews
        rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()
        for r in rows:
            p = json.loads(r[0])
            gid = p.get('graphMessageId') or p.get('internetMessageId')
            if gid and gid not in seen_gids:
                seen_gids.add(gid)
                accenture_emails.append({
                    'gid': gid,
                    'date': p.get('receivedDateTime') or '',
                    'subject': p.get('subject') or '',
                    'from': p.get('from') or p.get('client_lead_poc') or '',
                    'html': p.get('bodyHtml') or '',
                    'text': p.get('bodyText') or ''
                })
        conn.close()

    print(f"Total Accenture emails collected for dry run: {len(accenture_emails)}")
    
    # Extract raw table rows from each email
    headers_set = set()
    statuses_set = set()
    req_ids_list = []
    email_extracted_rows = [] # list of (email_info, row_dict)
    
    for email in sorted(accenture_emails, key=lambda x: x['date']):
        html = email['html']
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            continue
            
        # Parse main summary table (usually Table 0) or detail tables
        for t_idx, tbl in enumerate(tables):
            trs = tbl.find_all('tr')
            if not trs:
                continue
            
            headers = [td.get_text(strip=True) for td in trs[0].find_all(['th', 'td'])]
            # Check if trs[0] looks like a header (contains 'Request-ID' or 'Request ID' or 'Skills')
            has_req_id = any('req' in h.lower() and 'id' in h.lower() for h in headers)
            
            if has_req_id:
                headers_tuple = tuple(headers)
                headers_set.add(headers_tuple)
                for tr in trs[1:]:
                    cells = [td.get_text(strip=True) for td in tr.find_all(['td'])]
                    if len(cells) == len(headers) and cells[0]:
                        row_dict = dict(zip(headers, cells))
                        email_extracted_rows.append((email, row_dict))
                        req_id = cells[0].strip()
                        req_ids_list.append(req_id)
                        # Identify status column (Priority or Status)
                        status_val = row_dict.get('Priority') or row_dict.get('Status') or row_dict.get('job_status') or cells[-1]
                        statuses_set.add(status_val)
            else:
                # Reply emails might have single row tables with no header row in table 0
                first_cells = [td.get_text(strip=True) for td in trs[0].find_all(['td'])]
                if first_cells and re.match(r'^\d{5,8}(-\d+)?$', first_cells[0]):
                    # Single row table format
                    # Infer columns based on length
                    # Standard 8-col: Request-ID, Equivalent Grade, Skills - Name, Location Flex, RTO/Hybrid/WFH, Budget/monthly, Relevant Exp, Priority
                    # Standard 11-col: Request-ID, Equivalent Grade, Skills - Name, Location Flex, RTO/Hybrid/WFH, Budget/monthly, Relevant Exp, Education, Priority, No of profiles, SPOC
                    if len(first_cells) == 8:
                        std_headers = ['Request-ID', 'Equivalent Grade', 'Skills - Name', 'Location Flex', 'RTO/Hybrid/WFH', 'Budget/monthly', 'Relevant Exp', 'Priority']
                    elif len(first_cells) == 11:
                        std_headers = ['Request-ID', 'Equivalent Grade', 'Skills - Name', 'Location Flex', 'RTO/Hybrid/WFH', 'Budget/monthly', 'Relevant Exp', 'Education', 'Priority', 'No of profiles', 'SPOC']
                    elif len(first_cells) == 9:
                        std_headers = ['Request-ID', 'Equivalent Grade', 'Skills - Name', 'Location Flex', 'RTO/Hybrid/WFH', 'Budget/monthly', 'Relevant Exp', 'Education', 'Priority']
                    else:
                        std_headers = [f"Col_{i}" for i in range(len(first_cells))]
                    
                    row_dict = dict(zip(std_headers, first_cells))
                    email_extracted_rows.append((email, row_dict))
                    req_id = first_cells[0].strip()
                    req_ids_list.append(req_id)
                    status_val = row_dict.get('Priority') or row_dict.get('Status') or first_cells[-1]
                    statuses_set.add(status_val)

    print("\n--- EXACT TABLE COLUMN HEADERS ---")
    for h in headers_set:
        print("Header list:", list(h))

    print("\n--- EVERY STATUS / PRIORITY VALUE USED ---")
    print(sorted(list(statuses_set)))

    print("\n--- REQ ID FORMATS & REUSE CHECK ---")
    print(f"Total raw requirement rows extracted: {len(email_extracted_rows)}")
    distinct_req_ids = set(req_ids_list)
    print(f"Total distinct Req IDs: {len(distinct_req_ids)}")
    
    # Check if Req IDs are written differently
    id_patterns = set()
    for req_id in distinct_req_ids:
        # e.g., 195398-1
        pattern = re.sub(r'\d', 'N', req_id)
        id_patterns.add(pattern)
    print("Req ID patterns found:", id_patterns)

    # DRY RUN RULES (Rules 1-7)
    # 2. Req ID never seen before -> CREATE
    # 3. Req ID seen, nothing changed -> SKIP
    # 4. Req ID seen, status changed -> UPDATE
    # 5. Req ID seen, details changed -> UPDATE
    
    store = {} # req_id -> row_dict
    action_counts = {'create': 0, 'skip': 0, 'update': 0}
    action_log = []
    
    for email, row_dict in email_extracted_rows:
        req_id = row_dict.get('Request-ID') or row_dict.get('Request ID') or list(row_dict.values())[0]
        req_id = req_id.strip()
        
        if req_id not in store:
            store[req_id] = row_dict
            action_counts['create'] += 1
            action_log.append(('CREATE', req_id, email['date'], email['subject']))
        else:
            prev_row = store[req_id]
            # Compare prev_row vs row_dict
            if prev_row == row_dict:
                action_counts['skip'] += 1
                action_log.append(('SKIP', req_id, email['date'], email['subject']))
            else:
                # Check what changed
                prev_status = prev_row.get('Priority') or prev_row.get('Status')
                curr_status = row_dict.get('Priority') or row_dict.get('Status')
                store[req_id] = row_dict
                action_counts['update'] += 1
                action_log.append(('UPDATE', req_id, email['date'], f"Status: {prev_status}->{curr_status}"))

    print("\n--- DRY RUN RESULTS ---")
    print(f"Raw rows: {len(email_extracted_rows)}")
    print(f"Distinct Req IDs: {len(distinct_req_ids)}")
    print(f"Create actions: {action_counts['create']}")
    print(f"Skip actions: {action_counts['skip']}")
    print(f"Update actions: {action_counts['update']}")

    print("\nSample actions:")
    for a in action_log[:15]:
        print(" ", a)

if __name__ == '__main__':
    run_analysis()
