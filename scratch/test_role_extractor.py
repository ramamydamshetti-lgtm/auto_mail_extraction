import re
from bs4 import BeautifulSoup

def extract_role_and_id(html_or_text):
    if not html_or_text:
        return None, None
        
    client_id = None
    role = None
    
    # Check for HTML table
    if '<table' in html_or_text.lower():
        soup = BeautifulSoup(html_or_text, 'html.parser')
        tables = soup.find_all('table')
        for tbl in tables:
            trs = tbl.find_all('tr')
            for tr in trs:
                cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
                if cells and re.match(r'^\d{5,8}(-\d+)?$', cells[0]):
                    client_id = cells[0]
                    if len(cells) > 2 and len(cells[2]) > 2:
                        role = cells[2]
                        return client_id, role
                # Check for Request-ID: 209160-1
                if len(cells) >= 2 and 'request-id' in cells[0].lower():
                    m = re.search(r'\d{5,8}(-\d+)?', cells[1])
                    if m:
                        client_id = m.group(0)
                        
    # Check text patterns
    text = html_or_text
    if not client_id:
        m_id = re.search(r'\b(\d{5,8}-\d+)\b', text)
        if m_id:
            client_id = m_id.group(1)
            
    if not role:
        # Check "Must To Have Skills: Proficiency in <Role>"
        m_prof = re.search(r'Proficiency in ([^\.\n\r]+)', text, re.IGNORECASE)
        if m_prof:
            role = m_prof.group(1).strip()
            
    if not role:
        # Check "Comments for Suppliers:\s*([^R\n]+?)(?:Relevant|Location|\n|\r|$)"
        m_comm = re.search(r'Comments for Suppliers:\s*([^R\n\r]+)', text, re.IGNORECASE)
        if m_comm:
            candidate = m_comm.group(1).strip()
            if len(candidate) > 3 and not candidate.lower().startswith('gcc'):
                role = candidate
            elif 'relevant' in candidate.lower():
                role = candidate.split('relevant')[0].strip()

    return client_id, role

import sqlite3
import json

conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
for jid in ['2026/09/30-045', '2026/09/30-046']:
    r = conn.execute("SELECT payload_json FROM metaforge_requirements WHERE job_id = ?", (jid,)).fetchone()
    p = json.loads(r[0])
    body = p.get('bodyText') or p.get('body') or ""
    cid, role = extract_role_and_id(body)
    print(f"{jid}: extracted CID='{cid}', extracted Role='{role}'")
conn.close()
