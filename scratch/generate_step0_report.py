import csv
import json
import sqlite3
import os
import sys
from bs4 import BeautifulSoup
import re

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from email_filter import is_sender_allowlisted
from client_detector import detect_client

def run_step0_discovery():
    print("=== STEP 0a: ACCENTURE EMAILS IN latest_500_all.csv ===")
    accenture_emails_csv = []
    
    with open('latest_500_all.csv', 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            subj = row.get('subject') or ''
            from_e = (row.get('from_email') or '').strip()
            body = row.get('body_normalized') or ''
            full = f"{subj} {from_e} {body}".lower()
            client = detect_client(subj, body, from_e)
            
            if (client and client.key == 'accenture') or 'accenture' in full or 'anusha' in from_e.lower():
                domain = from_e.rsplit('@', 1)[-1].lower() if '@' in from_e else ''
                passes_allowlist = is_sender_allowlisted(from_e)
                accenture_emails_csv.append({
                    "row_index": idx,
                    "sender_address": from_e,
                    "sender_domain": domain,
                    "subject": subj,
                    "passes_allowlist": passes_allowlist
                })
                
    for e in accenture_emails_csv:
        print(f"Row {e['row_index']} | From: {e['sender_address']} ({e['sender_domain']}) | Subj: {e['subject']} | Passes Allowlist: {e['passes_allowlist']}")

    print("\n=== STEP 0b & 0c: TABLE STRUCTURE, REQ ID & STATUS COLUMNS, STATUS VALUES ===")
    conn = sqlite3.connect('data/processed_messages.db')
    cur = conn.cursor()
    rows = cur.execute("SELECT payload_json FROM pending_reviews WHERE payload_json LIKE '%accenture%'").fetchall()
    conn.close()
    
    distinct_statuses = set()
    req_id_formats = set()
    sample_table = None
    
    for r in rows:
        p = json.loads(r[0])
        html = p.get('bodyHtml')
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')
            for tbl in tables:
                trs = tbl.find_all('tr')
                if not trs:
                    continue
                headers = [td.get_text(strip=True) for td in trs[0].find_all(['th', 'td'])]
                if len(headers) >= 8 and any('req' in h.lower() and 'id' in h.lower() for h in headers):
                    if not sample_table:
                        req_col = [h for h in headers if 'req' in h.lower() and 'id' in h.lower()][0]
                        stat_col = [h for h in headers if 'priority' in h.lower() or 'status' in h.lower()][0]
                        sample_table = {
                            "exact_column_headers": headers,
                            "req_id_column": req_col,
                            "status_column": stat_col
                        }
                    for tr in trs[1:]:
                        cells = [td.get_text(strip=True) for td in tr.find_all(['td'])]
                        if len(cells) == len(headers) and cells[0]:
                            req_id = cells[0].strip()
                            if re.match(r'^\d{5,8}(-\d+)?$', req_id):
                                pattern = re.sub(r'\d', 'N', req_id)
                                req_id_formats.add(pattern)
                                stat = cells[-1]
                                if stat and stat not in ('SPOC', 'Harshitha', 'Sahil', 'Sanjay'):
                                    distinct_statuses.add(stat)

    print("Sample Table Structure:", json.dumps(sample_table, indent=2))
    print("Distinct Status Values Seen:", sorted(list(distinct_statuses)))
    print("Req ID Formats Seen:", list(req_id_formats))

    # STEP 0d: MetaForge Endpoint capability analysis
    metaforge_capability = {
        "sqlite_mode": "Supports UPDATE via INSERT OR REPLACE INTO metaforge_requirements (job_id, payload_json, created_at) VALUES (?,?,?).",
        "api_mode": "POST api/internal/requirements/ingest-email strictly ingests new payloads. It strips job_id and client_jd_id before posting. Posting identical client_jd_id returns {'deduped': True} and does NOT update existing record attributes or expose a HTTP PUT/PATCH update route.",
        "behavior_on_duplicate_post": "MetaForge API dedupes the request (ignores duplicate); SQLite updates in-place."
    }

    # Construct client_profiles.proposed.json structure
    proposed_profile = {
        "description": "Proposed client profile config store (Step 0 discovery, unactivated)",
        "clients": {
            "accenture": {
                "client_key": "accenture",
                "display_name": "Accenture",
                "enabled": True,
                "sender_domains": ["iexcel.co.in"],
                "sender_addresses": ["anusha.k@iexcel.co.in"],
                "table_req_id_headers": [
                    "Request-ID",
                    "Request ID",
                    "Req ID",
                    "Req-ID",
                    "ReqID",
                    "SO ID",
                    "Demand ID"
                ],
                "table_status_headers": [
                    "Priority",
                    "Status",
                    "Job Status",
                    "Demand Status"
                ],
                "status_mapping": {
                    "p1": "open",
                    "p2": "open",
                    "p3": "open",
                    "open": "open",
                    "hold": "hold",
                    "on hold": "hold",
                    "on-hold": "hold"
                },
                "req_id_normalization": {
                    "trim": True,
                    "case": "upper",
                    "pattern": r"^\d{5,8}(-\d+)?$"
                },
                "req_id_tracking": {
                    "enabled": True,
                    "bypass_24h_fingerprint": True
                }
            }
        },
        "discovery_findings": {
            "step_0a_accenture_emails_in_latest_500": accenture_emails_csv,
            "step_0b_sample_table": sample_table,
            "step_0b_distinct_statuses": sorted(list(distinct_statuses)),
            "step_0c_req_id_reused": True,
            "step_0c_req_id_patterns": list(req_id_formats),
            "step_0d_metaforge_capability": metaforge_capability
        }
    }

    with open('client_profiles.proposed.json', 'w', encoding='utf-8') as f:
        json.dump(proposed_profile, f, indent=2, ensure_ascii=False)

    print("\nWrote discovery findings to client_profiles.proposed.json (unactivated).")

if __name__ == '__main__':
    run_step0_discovery()
