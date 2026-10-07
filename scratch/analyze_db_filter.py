import sqlite3
import json
import sys
import os

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from email_filter import is_sender_allowlisted, has_requirement_structure, apply_email_filter, ALLOWED_CLIENT_DOMAINS

def test_db_accenture_emails():
    print("=== TESTING FILTER GATES ON ACCENTURE EMAILS IN DB ===")
    conn = sqlite3.connect('data/processed_messages.db')
    cur = conn.cursor()
    
    # Check filtered_log rows (38 emails)
    filtered_rows = cur.execute("SELECT id, graph_id, subject, from_email, reason, stage FROM filtered_log WHERE subject LIKE '%accenture%' OR from_email LIKE '%anusha%'").fetchall()
    
    print(f"Total Accenture emails in filtered_log: {len(filtered_rows)}")
    
    # We test with current ALLOWED_CLIENT_DOMAINS updated with 'iexcel.co.in'
    test_allowed_domains = {"ltts.com", "iexcel.co.in", "kpmg.com", "itcinfotech.com"}
    
    g1_pass = 0
    g2_pass = 0
    g3_pass = 0
    
    blocked_reasons = {}
    
    for r in filtered_rows:
        subj = r[2]
        from_e = r[3]
        
        # Check Gate 1: Allowlist
        domain = from_e.split('@', 1)[-1].lower() if '@' in from_e else ''
        g1 = any(domain == d or domain.endswith('.' + d) for d in test_allowed_domains)
        if not g1:
            reason = f"Gate 1 Blocked: sender_not_allowlisted ({from_e})"
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
            continue
        g1_pass += 1
        
        # Check Gate 2: requirement structure
        # Retrieve body from pending_reviews or payload if available
        p_row = cur.execute("SELECT payload_json FROM pending_reviews WHERE graph_id = ? LIMIT 1", (r[1],)).fetchone()
        body = ""
        if p_row:
            p = json.loads(p_row[0])
            body = p.get('bodyText') or p.get('bodyHtml') or ''
            
        g2 = has_requirement_structure(body) if body else False
        if not g2:
            reason = f"Gate 2 Blocked: no_requirement_structure_in_body (body_len={len(body)})"
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
            print(f"Row {r[0]} | Subj='{subj}' | From='{from_e}' -> Gate 2 Blocked")
            continue
        g2_pass += 1
        
        g3_res = apply_zero_skip_filter_mock(from_e, test_allowed_domains)
        g3_pass += 1
        
    print("\n--- DB FILTER SUMMARY ---")
    print(f"Total: {len(filtered_rows)}")
    print(f"Gate 1 Passed: {g1_pass}")
    print(f"Gate 2 Passed: {g2_pass}")
    print("Blocked Breakdown:")
    for b, c in blocked_reasons.items():
        print(f"  {b}: {c}")

def apply_zero_skip_filter_mock(from_e, domains):
    return True

if __name__ == '__main__':
    test_db_accenture_emails()
