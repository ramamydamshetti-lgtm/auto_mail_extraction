import csv
import json
import sys
import os
import re

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

def run_report():
    print("=== ITEM 3: DISTINCT SENDER DOMAINS CONTAINING 'iexcel' OR 'idexcel' IN latest_500_all.csv ===")
    domain_counts = {}
    
    with open('latest_500_all.csv', 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    for r in rows:
        from_e = (r.get('from_email') or '').strip().lower()
        if '@' in from_e:
            domain = from_e.split('@', 1)[1]
            if 'iexcel' in domain or 'idexcel' in domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                
    for dom, cnt in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {dom}: {cnt} email(s)")
    if not domain_counts:
        print("  No sender domains containing 'iexcel' or 'idexcel' found in latest_500_all.csv.")

    print("\n=== ITEM 4: REAL LIVE FILTER PATH ON ACCENTURE EMAILS IN latest_500_all.csv ===")
    from email_filter import is_sender_allowlisted, has_requirement_structure, apply_email_filter
    from client_detector import detect_client
    
    accenture_emails = []
    for idx, r in enumerate(rows):
        subj = r.get('subject') or ''
        from_e = r.get('from_email') or ''
        body = r.get('body_normalized') or ''
        full = f"{subj} {from_e} {body}".lower()
        
        # Check if detected as accenture or subject/from mentions accenture
        client = detect_client(subj, body, from_e)
        if (client and client.key == 'accenture') or 'accenture' in full or 'anusha' in from_e.lower():
            accenture_emails.append((idx, r, client))

    print(f"Total Accenture emails found in latest_500_all.csv: {len(accenture_emails)}")
    
    gate1_pass = 0
    gate2_pass = 0
    gate3_pass = 0
    
    blocked_reasons = {}
    
    for idx, r, client in accenture_emails:
        subj = r.get('subject') or ''
        from_e = r.get('from_email') or ''
        body = r.get('body_normalized') or ''
        has_att = bool(r.get('attachment_count') and int(r.get('attachment_count')) > 0)
        
        g1 = is_sender_allowlisted(from_e)
        if not g1:
            reason = f"Gate 1 Blocked: sender_not_allowlisted ({from_e})"
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
            print(f"Row {idx} | Subj='{subj}' | From='{from_e}' -> {reason}")
            continue
        gate1_pass += 1
        
        g2 = has_requirement_structure(body)
        if not g2:
            reason = f"Gate 2 Blocked: no_requirement_structure_in_body"
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
            print(f"Row {idx} | Subj='{subj}' | From='{from_e}' -> {reason}")
            continue
        gate2_pass += 1
        
        res = apply_email_filter(subject=subj, body=body, has_attachments=has_att, from_email=from_e)
        if not res.allowed:
            reason = f"Gate 3 Blocked: {res.reason}"
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
            print(f"Row {idx} | Subj='{subj}' | From='{from_e}' -> {reason}")
            continue
        gate3_pass += 1
        print(f"Row {idx} | Subj='{subj}' | From='{from_e}' -> PASSED ALL GATES")

    print("\n--- FILTER GATE SUMMARY ---")
    print(f"Total Accenture emails evaluated: {len(accenture_emails)}")
    print(f"Passed Gate 1 (sender_allowlisted): {gate1_pass}")
    print(f"Passed Gate 2 (has_requirement_structure): {gate2_pass}")
    print(f"Passed Gate 3 (apply_email_filter): {gate3_pass}")
    print("Blocked Breakdown:")
    for r, cnt in blocked_reasons.items():
        print(f"  {r}: {cnt}")

if __name__ == '__main__':
    run_report()
