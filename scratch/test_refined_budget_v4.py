import sqlite3
import json
import re

def parse_email_budget_v4(body):
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

    # Regex targeting:
    # "Monthly Bill Rate:"
    # "Bill Rate per month for TPC:"
    # "Bill rate per month - "
    # "Bill rate- "
    # "Bill Rate : "
    # "Billing Rate: "
    rate_pattern = re.compile(
        r'(?i)(?:^|[\r\n])\s*(?:monthly\s+bill\s+rate|monthly\s+billing\s+rate|monthly\s+budget|bill\s+rate|billing\s+rate)\s*(?:per\s+month(?:\s+for\s+tpc)?)?\s*(?:\([^)]*\))?\s*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+)?)'
    )
    
    for m in rate_pattern.finditer(text):
        chunk = m.group(1).strip()
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        for l in lines:
            if re.search(r'(?i)\b(years?|yrs?|experience|qualification|location|shift|customer|immediate)\b', l):
                continue
            # Range e.g. "150000 - 200000", "85 K - 1L / M", "200000-220000 max", "120000 – 140000"
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

def test_v4():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    extracted_count = 0
    samples = []
    
    for r in rows:
        p = json.loads(r['payload_json'])
        curr_mb = p.get('monthly_budget')
        body = p.get('bodyText') or p.get('body') or ""
        
        extracted, low, high, curr = parse_email_budget_v4(body)
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
    test_v4()
