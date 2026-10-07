import sqlite3
import json
import os
import re

def analyze_all():
    db_path = 'data/metaforge_requirements.db'
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return

    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    total = len(rows)
    print(f"Total rows in metaforge_requirements: {total}")
    
    missing_budget = 0
    recoverable_budget = 0
    disclaimer_notice = 0
    polluted_skills = 0
    
    sample_recoverable = []
    sample_disclaimers = []
    
    for r in rows:
        p = json.loads(r['payload_json'])
        body = p.get('bodyText') or p.get('body') or ""
        
        # Check budget
        mb = p.get('monthly_budget')
        if not mb:
            missing_budget += 1
            # Check if recoverable
            if re.search(r'(?i)\b(bill\s*rate|billing|rate\s*/\s*pm|monthly\s*(?:budget|bill|rate))\b', body):
                recoverable_budget += 1
                if len(sample_recoverable) < 10:
                    sample_recoverable.append((r['job_id'], r['client_jd_id']))
                    
        # Check notice period
        np = str(p.get('notice_period') or '').strip().lower()
        if any(w in np for w in ['e-mail message', 'confidential', 'attachment', 'intended recipient', 'privilege', 'unauthorized', 'dissemination']):
            disclaimer_notice += 1
            sample_disclaimers.append((r['job_id'], r['client_jd_id'], p.get('notice_period')))
            
        # Check skills pollution
        skills = p.get('skills') or []
        if isinstance(skills, list):
            polluted = [s for s in skills if any(w in str(s).lower() for w in ['technologies', 'pvt ltd', 'iso 27001', 'bhuvanappa', 'hosur', 'bengaluru', 'mob:', 'http', 'talent acquisition'])]
            if polluted:
                polluted_skills += 1
                
    print(f"Missing monthly_budget: {missing_budget}/{total}")
    print(f"Recoverable monthly_budget in text: {recoverable_budget}/{total}")
    print(f"Disclaimer contaminated notice_period: {disclaimer_notice}/{total}")
    print(f"Polluted skills lists: {polluted_skills}/{total}")
    
    if sample_disclaimers:
        print("\nSample contaminated notice periods:")
        for s in sample_disclaimers[:5]:
            print(f"  {s[0]} ({s[1]}): {s[2]}")
            
    conn.close()

if __name__ == '__main__':
    analyze_all()
