import json
import re
import sqlite3

def clean_notice(np):
    if not np:
        return None
    s = str(np).strip()
    if any(junk in s.lower() for junk in [
        "this e-mail message", "confidentiality", "intended recipient", 
        "unauthorized review", "please contact the sender", "destroy all copies",
        "none", "null", "not specified", "n/a"
    ]):
        return None
    return s

def extract_budget_from_text(text):
    """Scan email body for monthly budget, bill rate, or budget range."""
    if not text:
        return None, None, None
        
    # Match patterns like:
    # Monthly Bill Rate: 150000 - 200000
    # Monthly Bill Rate:\n150000 - 200000
    # Monthly Bill Rate: 75000 – 1,00,000
    # 2.79 Lakhs
    # 3.50 Lakhs(Budget Flex)
    # 279067(Budget Flex)
    # 380,380
    
    # 1. Direct "Monthly Bill Rate" or "Monthly Budget" or "Bill Rate"
    m_rate = re.search(r'(?i)(?:monthly\s+(?:bill\s+rate|billing\s+rate|budget)|bill\s+rate|billing\s+rate)\s*[:\-]?\s*([^\n\r]+(?:\n[^\n\r]+)?)', text)
    if m_rate:
        target = m_rate.group(1).strip()
        # Look for numbers in target
        m_range = re.search(r'(\d[\d,\.]*)\s*(?:–|-|to)\s*(\d[\d,\.]*)', target)
        if m_range:
            low = m_range.group(1).replace(',', '').strip()
            high = m_range.group(2).replace(',', '').strip()
            return f"{low} - {high}", low, high
        m_single = re.search(r'(\d[\d,\.]*)\s*(?:lakhs?|lpa|lpm)?', target)
        if m_single and len(m_single.group(1).replace('.', '')) >= 4:
            val = m_single.group(1).replace(',', '').strip()
            return val, val, val
            
    # 2. Look for Lakhs / per month
    m_lakh = re.search(r'(\d+(?:\.\d+)?)\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*(?:lakhs?|lpm)', text, re.IGNORECASE)
    if m_lakh:
        return f"{m_lakh.group(1)} - {m_lakh.group(2)} Lakhs", m_lakh.group(1), m_lakh.group(2)
        
    m_lakh_single = re.search(r'(\d+(?:\.\d+)?)\s*lakhs?(?:\s*\([^)]*\))?', text, re.IGNORECASE)
    if m_lakh_single:
        return m_lakh_single.group(0).strip(), None, None

    return None, None, None

def main():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    missing_budget_found = 0
    bad_notice_found = 0
    
    print(f"Total rows in metaforge_requirements: {len(rows)}")
    
    for i, r in enumerate(rows):
        p = json.loads(r['payload_json'])
        body = p.get('bodyText') or p.get('body') or ""
        
        # Check budget
        curr_mb = p.get('monthly_budget')
        curr_yb = p.get('yearly_budget')
        if not curr_mb and not curr_yb:
            found_b, low, high = extract_budget_from_text(body)
            if found_b:
                missing_budget_found += 1
                if missing_budget_found <= 10:
                    print(f"[BUDGET RECOVERABLE] Req ID: {r['job_id']} / {p.get('client_jd_id')}: Found in text: '{found_b}'")
                    
        # Check notice period
        curr_np = p.get('notice_period')
        cleaned = clean_notice(curr_np)
        if curr_np and cleaned != curr_np:
            bad_notice_found += 1
            if bad_notice_found <= 5:
                print(f"[BAD NOTICE PERIOD] Req ID: {r['job_id']}: '{curr_np}' -> None")
                
    print(f"\nSummary:")
    print(f"  Missing budgets recoverable from email body: {missing_budget_found}")
    print(f"  Bad/junk notice periods: {bad_notice_found}")
    conn.close()

if __name__ == "__main__":
    main()
