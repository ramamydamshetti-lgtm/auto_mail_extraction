import sqlite3
import json
import re

def parse_email_budget(body):
    if not body:
        return None, None, None, None
        
    text = body
    
    # Normalizing non-breaking spaces
    text = text.replace('\xa0', ' ')
    
    # 1. Pattern: Multi-line or single-line "Monthly Bill Rate:" / "Bill Rate:" / "Monthly Budget:" / "Rate / pm:"
    # Notice: can be followed by newline, spaces, dashes, etc.
    # E.g.:
    # "Monthly Bill Rate:\n150000 - 200000"
    # "Bill Rate : 85 K - 1L / M"
    # "Bill Rate per month for TPC: 80 K / M"
    # "Bill Rate-60000 max"
    # "Bill rate- 135000/month"
    # "Bill Rate-200000-220000 max"
    # "Bill Rate per month for TPC (in terms of INR)-\n94 K"
    # "Bill Rate per month for TPC (in terms of INR)-\n150000"
    # "Bill Rate – 120000 – 140000"
    # "Bill rate per month - 1.50 L / M"
    # "4 – 5 yrs – 1.4 L\n5 – 6 yrs – 1.65 L"
    
    # Regex to capture rate chunk following a label
    rate_label_regex = re.compile(
        r'(?i)(?:monthly\s+(?:bill\s+rate|billing\s+rate|budget|rate)|bill\s+rate|billing\s+rate|rate\s*/\s*pm(?:[^\n\r]*inr)?)\s*[:\-–]?\s*([^\r\n]+(?:\r?\n[^\r\n]+){0,2})'
    )
    
    for match in rate_label_regex.finditer(text):
        chunk = match.group(1).strip()
        
        # Check if chunk starts with non-budget text (e.g. next section)
        first_line = chunk.splitlines()[0].strip()
        
        # Handle "85 K - 1L / M" or "1.50 L / M" or "150000 - 200000" or "94 K" or "60000 max"
        # First check for range with K/L/Lakhs/raw numbers
        m_range = re.search(
            r'(\d+(?:\.\d+)?)\s*(k|l|lakhs?|lpm)?\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*(k|l|lakhs?|lpm)?',
            chunk, re.IGNORECASE
        )
        if m_range:
            v1_str, u1, v2_str, u2 = m_range.group(1), m_range.group(2), m_range.group(3), m_range.group(4)
            unit = (u2 or u1 or '').lower()
            try:
                v1 = float(v1_str)
                v2 = float(v2_str)
                
                # Determine scaling for v1 and v2
                u1_low = (u1 or '').lower()
                u2_low = (u2 or '').lower()
                
                def scale(val, u, default_u):
                    eff_u = u or default_u
                    if eff_u == 'k':
                        return int(val * 1000)
                    elif 'l' in eff_u:
                        return int(val * 100000)
                    elif val < 50: # Likely Lakhs (e.g. 1.5 - 2)
                        return int(val * 100000)
                    elif val < 1000: # E.g. 85 - 100 (if with 1L or 85k)
                        return int(val * 1000)
                    return int(val)
                    
                low_val = scale(v1, u1_low, u2_low)
                high_val = scale(v2, u2_low, u1_low)
                
                if 10000 <= low_val <= 10000000 and 10000 <= high_val <= 10000000:
                    display = f"{low_val} - {high_val}"
                    return display, low_val, high_val, "INR"
            except Exception:
                pass
                
        # Check for single value: e.g. "94 K" or "150000" or "1.50 L / M" or "80 K / M" or "60000 max" or "135000/month"
        m_single = re.search(
            r'(?:^|[\s:\-–])(\d+(?:\.\d+)?)\s*(k|l|lakhs?|lpm)?(?:\s*/\s*m(?:onth)?)?(?:\s*max)?',
            chunk, re.IGNORECASE
        )
        if m_single:
            v_str, u = m_single.group(1), m_single.group(2)
            unit = (u or '').lower()
            try:
                v = float(v_str)
                if unit == 'k':
                    val = int(v * 1000)
                elif 'l' in unit:
                    val = int(v * 100000)
                elif v < 50:
                    val = int(v * 100000)
                else:
                    val = int(v)
                    
                if 10000 <= val <= 10000000:
                    return str(val), val, val, "INR"
            except Exception:
                pass

    return None, None, None, None

def run_test():
    conn = sqlite3.connect('file:data/metaforge_requirements.db?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM metaforge_requirements").fetchall()
    
    extracted_count = 0
    samples = []
    
    for r in rows:
        p = json.loads(r['payload_json'])
        curr_mb = p.get('monthly_budget')
        body = p.get('bodyText') or p.get('body') or ""
        
        extracted, low, high, curr = parse_email_budget(body)
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
    run_test()
