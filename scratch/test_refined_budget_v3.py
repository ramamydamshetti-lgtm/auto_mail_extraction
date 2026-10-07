import sqlite3
import json
import re

def parse_email_budget_v3(body):
    if not body:
        return None, None, None, None
        
    text = body.replace('\xa0', ' ')
    
    def convert_val(val_str, unit_str):
        v = float(val_str.replace(',', '').strip())
        u = (unit_str or '').lower().strip()
        if u == 'k':
            return int(v * 1000)
        elif 'l' in u:
            return int(v * 100000)
        elif v < 50: # E.g. 1.5 - 2 or 1.5 LPM
            return int(v * 100000)
        elif v < 1000: # E.g. 85 in "85 - 100 K"
            return int(v * 1000)
        else:
            return int(v)

    # 1. Direct "Monthly Bill Rate:" (like RQ056293)
    m_monthly = re.search(
        r'(?i)monthly\s+(?:bill\s+rate|billing\s+rate|budget|rate)\s*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)',
        text
    )
    if m_monthly:
        chunk = m_monthly.group(1).strip()
        if not re.search(r'(?i)\b(years?|yrs?|exp|experience|location|qualification)\b', chunk):
            # Check for range: e.g. 150000 - 200000 or 1.5 - 2 LPM or 75000 – 1,00,000 or 85 K - 1 L
            m_rng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', chunk, re.IGNORECASE)
            if m_rng:
                try:
                    s1, u1 = m_rng.group(1), m_rng.group(2)
                    s2, u2 = m_rng.group(3), m_rng.group(4)
                    # if only one side had unit, inherit
                    eff_u1 = u1 or (u2 if float(s1.replace(',','')) < 1000 and u2 == 'k' else '')
                    eff_u2 = u2 or (u1 if float(s2.replace(',','')) < 1000 and u1 == 'k' else '')
                    low_val = convert_val(s1, eff_u1)
                    high_val = convert_val(s2, eff_u2)
                    if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                        return f"{low_val} - {high_val}", low_val, high_val, "INR"
                except Exception:
                    pass
            # Single value
            m_sng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?(?:\s*/\s*m(?:onth)?)?', chunk, re.IGNORECASE)
            if m_sng:
                try:
                    val = convert_val(m_sng.group(1), m_sng.group(2))
                    if 10000 <= val <= 10000000:
                        return str(val), val, val, "INR"
                except Exception:
                    pass

    # 2. Specific "Bill Rate" lines
    for line_match in re.finditer(r'(?i)(?:^|[\r\n])\s*(?:bill\s+rate|billing\s+rate)\b[^\r\n]*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)', text):
        chunk = line_match.group(1).strip()
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        for l in lines:
            if re.search(r'(?i)\b(years?|yrs?|experience|qualification|location|shift|customer|immediate)\b', l):
                continue
            # Range e.g. "85 K - 1L / M", "200000-220000 max", "120000 – 140000"
            m_rng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', l, re.IGNORECASE)
            if m_rng:
                try:
                    s1, u1 = m_rng.group(1), m_rng.group(2)
                    s2, u2 = m_rng.group(3), m_rng.group(4)
                    eff_u1 = u1 or (u2 if float(s1.replace(',','')) < 1000 and u2 == 'k' else '')
                    eff_u2 = u2 or (u1 if float(s2.replace(',','')) < 1000 and u1 == 'k' else '')
                    low_val = convert_val(s1, eff_u1)
                    high_val = convert_val(s2, eff_u2)
                    if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                        return f"{low_val} - {high_val}", low_val, high_val, "INR"
                except Exception:
                    pass
            # Single value e.g. "94 K", "150000", "1.50 L / M", "60000 max", "135000/month", "80 K / M"
            m_sng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?(?:\s*/\s*m(?:onth)?)?', l, re.IGNORECASE)
            if m_sng:
                try:
                    val = convert_val(m_sng.group(1), m_sng.group(2))
                    if 10000 <= val <= 10000000:
                        return str(val), val, val, "INR"
                except Exception:
                    pass

    return None, None, None, None

def test_v3():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    extracted_count = 0
    samples = []
    
    for r in rows:
        p = json.loads(r['payload_json'])
        curr_mb = p.get('monthly_budget')
        body = p.get('bodyText') or p.get('body') or ""
        
        extracted, low, high, curr = parse_email_budget_v3(body)
        if extracted:
            extracted_count += 1
            if len(samples) < 35:
                samples.append((r['job_id'], r['client_jd_id'], p.get('requirement_from'), extracted))
                
        if r['client_jd_id'] == 'RQ056293':
            print(f"*** TARGET RQ056293 ***")
            print(f"Current monthly_budget: {curr_mb}")
            print(f"Extracted budget: {extracted} (min={low}, max={high}, curr={curr})")
            
    print(f"\nTotal extracted: {extracted_count} out of {len(rows)}")
    print("\nSamples:")
    for s in samples:
        print(f"  {s[0]} | {s[1]} | {s[2]} -> {s[3]}")
        
    conn.close()

if __name__ == '__main__':
    test_v3()
