import sqlite3
import json
import os
import re

def parse_email_budget(body):
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
        elif v < 50:  # E.g. 1.5 - 2 or 1.5 LPM
            return int(v * 100000)
        elif v < 1000:  # E.g. 85 in "85 - 100 K"
            return int(v * 1000)
        else:
            return int(v)

    # Regex targeting rate labels:
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
                    eff_u1 = u1 or (u2 if float(s1.replace(',', '')) < 1000 and u2 == 'k' else '')
                    eff_u2 = u2 or (u1 if float(s2.replace(',', '')) < 1000 and u1 == 'k' else '')
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

def clean_notice_period(np_val):
    if not np_val:
        return None
    s = str(np_val).strip()
    if not s or s.lower() in ('none', 'null', 'not specified', 'n/a'):
        return None
    if re.search(r'(?i)\b(this e-?mail|confidential|attachment|intended recipient|privilege|unauthorized|dissemination|disclaimer)\b', s):
        return None
    return s

def clean_skills(skills_val):
    if not skills_val:
        return skills_val
    if isinstance(skills_val, list):
        cleaned = []
        for sk in skills_val:
            s_str = str(sk).strip()
            if not s_str:
                continue
            if re.search(r'(?i)(?:technologies|pvt\s+ltd|iso\s*27001|bhuvanappa|layout|hosur|road|bengaluru|bangalore|mob:|tel:|http|talent\s+acquisition|lead\s*-|idexcel|deloitte|metaforge|accenture|recruiter|hr\s+team|@iexcel|@idexcel)', s_str):
                continue
            cleaned.append(sk)
        return cleaned
    return skills_val

def repair_databases():
    db_paths = ['data/metaforge_requirements.db', 'data/processed_messages.db']
    
    total_updated = 0
    budget_added = 0
    np_cleaned = 0
    skills_cleaned = 0
    status_cleaned = 0
    
    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for tbl in ['metaforge_requirements', 'client_requirements', 'pending_reviews', 'requirement_memory']:
            if tbl not in tables:
                continue
            rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            row_keys = rows[0].keys() if rows else []
            id_col = 'job_id' if 'job_id' in row_keys else ('id' if 'id' in row_keys else None)
            if not id_col:
                continue
                
            for r in rows:
                p = json.loads(r['payload_json'])
                changed = False
                
                # 1. Budget recovery
                curr_mb = p.get('monthly_budget')
                if not curr_mb:
                    body = p.get('bodyText') or p.get('body') or ""
                    extracted, low, high, curr = parse_email_budget(body)
                    if extracted:
                        p['monthly_budget'] = extracted
                        p['monthly_budget_min'] = low
                        p['monthly_budget_max'] = high
                        if not p.get('budget_currency'):
                            p['budget_currency'] = curr or "INR"
                        changed = True
                        budget_added += 1
                        
                # 2. Notice period cleaning
                old_np = p.get('notice_period')
                cleaned_np = clean_notice_period(old_np)
                if old_np != cleaned_np:
                    p['notice_period'] = cleaned_np
                    changed = True
                    np_cleaned += 1
                    
                # 3. Skills cleaning
                old_skills = p.get('skills')
                cleaned_sk = clean_skills(old_skills)
                if old_skills != cleaned_sk:
                    p['skills'] = cleaned_sk
                    changed = True
                    skills_cleaned += 1
                    
                # 4. Job status cleaning
                old_status = str(p.get('job_status') or '').strip().lower()
                if old_status not in ('open', 'hold', 'closed', 'reopen', 'active', 'cancelled', 'on hold', 'on-hold') or len(old_status) > 20:
                    p['job_status'] = 'open'
                    p['requirement_status'] = 'open'
                    changed = True
                    status_cleaned += 1
                    
                # 5. Internal POC Email fallback
                if not p.get('internal_poc_email') and p.get('to'):
                    to_val = str(p.get('to')).strip()
                    if '@' in to_val:
                        p['internal_poc_email'] = to_val
                        changed = True
                        
                # 6. Ensure receivedDateTime has full ISO timestamp
                if 'created_at' in row_keys and r['created_at']:
                    cre = str(r['created_at']).strip()
                    if 'T' in cre and (not p.get('receivedDateTime') or len(str(p.get('receivedDateTime'))) == 10):
                        p['receivedDateTime'] = cre
                        changed = True
                        
                if changed:
                    conn.execute(
                        f"UPDATE {tbl} SET payload_json = ? WHERE {id_col} = ?",
                        (json.dumps(p, ensure_ascii=False), r[id_col])
                    )
                    total_updated += 1
                    
            conn.commit()
        conn.close()
        
    print(f"Repair complete:")
    print(f"  Total records updated: {total_updated}")
    print(f"  Budgets recovered: {budget_added}")
    print(f"  Notice periods cleaned: {np_cleaned}")
    print(f"  Skills cleaned: {skills_cleaned}")
    print(f"  Statuses cleaned: {status_cleaned}")

if __name__ == '__main__':
    repair_databases()
