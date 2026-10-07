import sqlite3
import json
import re

def parse_email_budget_v2(body):
    if not body:
        return None, None, None, None
        
    text = body.replace('\xa0', ' ')
    
    # 1. Direct "Monthly Bill Rate:" (like RQ056293)
    # Monthly Bill Rate:\n150000 - 200000
    # Monthly Bill Rate: 150000 - 200000
    # Monthly Billing Rate: ...
    # Monthly Budget: ...
    m_monthly = re.search(
        r'(?i)monthly\s+(?:bill\s+rate|billing\s+rate|budget|rate)\s*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)',
        text
    )
    if m_monthly:
        chunk = m_monthly.group(1).strip()
        # Ensure chunk doesn't say "years" or "exp"
        if not re.search(r'(?i)\b(years?|yrs?|exp|experience)\b', chunk):
            # Check for range: e.g. 150000 - 200000 or 1.5 - 2 LPM or 75000 – 1,00,000
            m_rng = re.search(r'(\d[\d,\.]*)\s*(?:k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', chunk, re.IGNORECASE)
            if m_rng:
                s1 = m_rng.group(1).replace(',', '').strip()
                s2 = m_rng.group(2).replace(',', '').strip()
                try:
                    v1 = float(s1)
                    v2 = float(s2)
                    if v1 < 50 and v2 < 50:
                        v1 *= 100000
                        v2 *= 100000
                    low_val = int(v1)
                    high_val = int(v2)
                    if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                        return f"{low_val} - {high_val}", low_val, high_val, "INR"
                except Exception:
                    pass
            # Single value
            m_sng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', chunk, re.IGNORECASE)
            if m_sng:
                s1 = m_sng.group(1).replace(',', '').strip()
                unit = (m_sng.group(2) or '').lower()
                try:
                    v1 = float(s1)
                    if unit == 'k':
                        v1 *= 1000
                    elif 'l' in unit or v1 < 50:
                        v1 *= 100000
                    val = int(v1)
                    if 10000 <= val <= 10000000:
                        return str(val), val, val, "INR"
                except Exception:
                    pass

    # 2. Specific "Bill Rate" lines (like LTTS: "Bill Rate-60000 max", "Bill Rate : 85 K - 1L / M", "Bill Rate per month for TPC:\n94 K")
    # Search each line or block starting with "Bill Rate" or "Billing Rate"
    for line_match in re.finditer(r'(?i)(?:^|[\r\n])\s*(?:bill\s+rate|billing\s+rate)\b[^\r\n]*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)', text):
        chunk = line_match.group(1).strip()
        # Skip if it's purely "Bill Rate per month for TPC (in terms of INR)-" and next line is "Work location"
        # Check first 2 lines
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        for l in lines:
            if re.search(r'(?i)\b(years?|yrs?|experience|qualification|location|shift|customer)\b', l):
                continue
            # Range e.g. "85 K - 1L / M", "200000-220000 max", "120000 – 140000"
            m_rng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?', l, re.IGNORECASE)
            if m_rng:
                s1, u1, s2, u2 = m_rng.group(1).replace(',', ''), m_rng.group(2), m_rng.group(3).replace(',', ''), m_rng.group(4)
                try:
                    v1, v2 = float(s1), float(s2)
                    eff_u = (u2 or u1 or '').lower()
                    if eff_u == 'k' or (v1 > 50 and v1 < 1000):
                        v1 = int(v1 * 1000) if v1 < 1000 else int(v1)
                        v2 = int(v2 * 1000) if v2 < 1000 else int(v2)
                    elif 'l' in eff_u or v1 < 50:
                        v1 = int(v1 * 100000) if v1 < 50 else int(v1)
                        v2 = int(v2 * 100000) if v2 < 50 else int(v2)
                    low_val, high_val = int(v1), int(v2)
                    if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                        return f"{low_val} - {high_val}", low_val, high_val, "INR"
                except Exception:
                    pass
            # Single value e.g. "94 K", "150000", "1.50 L / M", "60000 max", "135000/month", "80 K / M"
            m_sng = re.search(r'(\d[\d,\.]*)\s*(k|l|lakhs?|lpm)?(?:\s*/\s*m(?:onth)?)?', l, re.IGNORECASE)
            if m_sng:
                s1, u1 = m_sng.group(1).replace(',', ''), m_sng.group(2)
                try:
                    v1 = float(s1)
                    eff_u = (u1 or '').lower()
                    if eff_u == 'k':
                        v1 *= 1000
                    elif 'l' in eff_u or v1 < 50:
                        v1 *= 100000
                    val = int(v1)
                    if 10000 <= val <= 10000000:
                        return str(val), val, val, "INR"
                except Exception:
                    pass

    return None, None, None, None

def test_v2():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    extracted_count = 0
    samples = []
    
    for r in rows:
        p = json.loads(r['payload_json'])
        curr_mb = p.get('monthly_budget')
        body = p.get('bodyText') or p.get('body') or ""
        
        extracted, low, high, curr = parse_email_budget_v2(body)
        if extracted:
            extracted_count += 1
            if len(samples) < 25:
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
    test_v2()
