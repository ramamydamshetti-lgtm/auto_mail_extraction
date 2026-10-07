import json
import re
import sqlite3

def parse_email_budget(body):
    if not body:
        return None, None, None, None
        
    text = body
    
    # 1. Multi-line or single-line "Monthly Bill Rate:" or "Monthly Billing Rate:" or "Monthly Budget:"
    # Examples:
    # Monthly Bill Rate:\n150000 - 200000
    # Monthly Bill Rate: 75000 – 1,00,000
    # Monthly Bill Rate: 130000
    # Monthly Bill Rate: 1.5 - 2 LPM
    m1 = re.search(r'(?i)(?:monthly\s+(?:bill\s+rate|billing\s+rate|budget)|bill\s+rate|billing\s+rate|monthly\s+rate)\s*[:\-]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)', text)
    if m1:
        chunk = m1.group(1).strip()
        # Look for range like 150000 - 200000 or 75000 – 1,00,000 or 1.5 - 2 LPM
        m_range = re.search(r'(\d[\d,\.]*)\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(?:lakhs?|lpm|lpa)?', chunk, re.IGNORECASE)
        if m_range:
            low_s = m_range.group(1).replace(',', '').strip()
            high_s = m_range.group(2).replace(',', '').strip()
            try:
                low = float(low_s)
                high = float(high_s)
                # If numbers are like 1.5 - 2
                if low < 100:  # in Lakhs
                    low_val = int(low * 100000)
                    high_val = int(high * 100000)
                else:
                    low_val = int(low)
                    high_val = int(high)
                display = f"150000 - 200000" if (low_val==150000 and high_val==200000) else f"{low_val} - {high_val}"
                return display, low_val, high_val, "INR"
            except Exception:
                pass
                
        # Look for single value like 130000 or 2.79 Lakhs
        m_val = re.search(r'(\d[\d,\.]*)\s*(lakhs?|lpm|lpa)?', chunk, re.IGNORECASE)
        if m_val:
            s = m_val.group(1).replace(',', '').strip()
            unit = (m_val.group(2) or '').lower()
            try:
                num = float(s)
                if 'lakh' in unit or 'lpm' in unit or num < 100:
                    val = int(num * 100000) if num < 100 else int(num)
                else:
                    val = int(num)
                if val >= 10000:
                    return str(val), val, val, "INR"
            except Exception:
                pass

    # 2. Pattern: "X - Y Lakhs" or "X Lakhs"
    m_lakhs_range = re.search(r'(\d+(?:\.\d+)?)\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*lakhs?', text, re.IGNORECASE)
    if m_lakhs_range:
        try:
            l = int(float(m_lakhs_range.group(1)) * 100000)
            h = int(float(m_lakhs_range.group(2)) * 100000)
            return f"{l} - {h}", l, h, "INR"
        except Exception:
            pass

    m_lakhs_single = re.search(r'(\d+(?:\.\d+)?)\s*lakhs?(?:\s*\([^)]*\))?', text, re.IGNORECASE)
    if m_lakhs_single:
        # Avoid experience or notice matches
        prefix = text[max(0, m_lakhs_single.start() - 30):m_lakhs_single.start()].lower()
        if 'exp' not in prefix and 'year' not in prefix:
            try:
                val = int(float(m_lakhs_single.group(1)) * 100000)
                raw_txt = m_lakhs_single.group(0).strip()
                return raw_txt, val, val, "INR"
            except Exception:
                pass

    # 3. Pattern: "Rate / pm (INR): X" or "Rate / pm: X"
    m_pm = re.search(r'(?i)rate\s*\/\s*pm[^\d]*(\d[\d,\.]*)', text)
    if m_pm:
        s = m_pm.group(1).replace(',', '').strip()
        try:
            val = int(float(s))
            if val >= 10000:
                return str(val), val, val, "INR"
        except Exception:
            pass

    return None, None, None, None

def test():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    found_count = 0
    for r in rows:
        p = json.loads(r['payload_json'])
        curr_mb = p.get('monthly_budget')
        body = p.get('bodyText') or p.get('body') or ""
        extracted, low, high, curr = parse_email_budget(body)
        
        if r['client_jd_id'] == 'RQ056293' or 'RQ056293' in r['payload_json']:
            print(f"*** TARGET RQ056293 ***")
            print(f"Current monthly_budget: {curr_mb}")
            print(f"Extracted budget: {extracted} (min={low}, max={high}, curr={curr})")
            
        if not curr_mb and extracted:
            found_count += 1
            if found_count <= 8:
                print(f"Req: {r['job_id']} (Client: {p.get('requirement_from')}): extracted '{extracted}'")
                
    print(f"\nTotal missing budgets recovered: {found_count} out of {len(rows)} records")
    conn.close()

if __name__ == "__main__":
    test()
