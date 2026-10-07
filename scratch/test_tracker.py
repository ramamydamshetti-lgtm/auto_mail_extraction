import sqlite3
import json
import hashlib
import sys
import os
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# Mock ProcessedStore table structure in memory/test
class ClientRequirementsTracker:
    def __init__(self):
        self.store = {} # client_jd_id -> dict

    def evaluate_and_update(self, client_jd_id, status, payload_dict):
        # Create hash of details (excluding dynamic timestamps/IDs)
        details = {
            'job_title': payload_dict.get('job_title'),
            'location': payload_dict.get('location'),
            'experience': payload_dict.get('overall_experience') or payload_dict.get('experience'),
            'budget': payload_dict.get('monthly_budget') or payload_dict.get('yearly_budget'),
            'mandatory_skills': payload_dict.get('mandatory_skills'),
            'status': status.lower()
        }
        details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode('utf-8')).hexdigest()
        
        if client_jd_id not in self.store:
            self.store[client_jd_id] = {
                'status': status.lower(),
                'hash': details_hash,
                'payload': payload_dict
            }
            return 'CREATE'
            
        existing = self.store[client_jd_id]
        if existing['status'] != status.lower() or existing['hash'] != details_hash:
            self.store[client_jd_id] = {
                'status': status.lower(),
                'hash': details_hash,
                'payload': payload_dict
            }
            return 'UPDATE'
            
        return 'SKIP'

def run_test():
    conn = sqlite3.connect('data/processed_messages.db')
    cur = conn.cursor()
    rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()
    conn.close()
    
    # Sort emails by date
    parsed_reqs = []
    seen_gids = set()
    for r in rows:
        p = json.loads(r[0])
        gid = p.get('graphMessageId') or p.get('internetMessageId')
        dt = p.get('receivedDateTime') or ''
        html = p.get('bodyHtml')
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')
            for tbl in tables:
                trs = tbl.find_all('tr')
                for tr in trs:
                    cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    if cells and cells[0] and len(cells) >= 8:
                        req_id = cells[0].strip()
                        if req_id != 'Request-ID' and req_id.replace('-', '').isdigit():
                            status = cells[-1] if len(cells) in (8, 11) else cells[-2]
                            parsed_reqs.append({
                                'date': dt,
                                'req_id': req_id,
                                'status': status,
                                'cells': cells
                            })

    parsed_reqs.sort(key=lambda x: x['date'])
    print(f"Total raw Accenture table rows parsed chronologically: {len(parsed_reqs)}")
    
    tracker = ClientRequirementsTracker()
    counts = {'CREATE': 0, 'SKIP': 0, 'UPDATE': 0}
    
    for item in parsed_reqs:
        req_id = item['req_id']
        status = item['status']
        action = tracker.evaluate_and_update(req_id, status, {'job_title': item['cells'][2], 'location': item['cells'][3], 'status': status})
        counts[action] += 1
        
    print(f"Distinct Req IDs: {len(tracker.store)}")
    print(f"Counts: CREATE={counts['CREATE']}, SKIP={counts['SKIP']}, UPDATE={counts['UPDATE']}")

if __name__ == '__main__':
    run_test()
