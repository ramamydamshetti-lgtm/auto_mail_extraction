import os
import sys
import sqlite3
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('.'))
load_dotenv()

mailbox = os.getenv("MAILBOX_UPN", "recruitment.application@metaforgeit.com")

# 1. Purge KPMG test data from metaforge_requirements.db and processed_messages.db
db_meta = 'data/metaforge_requirements.db'
if os.path.exists(db_meta):
    conn = sqlite3.connect(db_meta)
    cur = conn.cursor()
    cur.execute("DELETE FROM metaforge_requirements WHERE payload_json LIKE '%REQ-998811%' OR payload_json LIKE '%MSG-TEST-%'")
    print(f"Deleted KPMG test rows from metaforge_requirements: {cur.rowcount}")
    conn.commit()
    conn.close()

db_proc = 'data/processed_messages.db'
if os.path.exists(db_proc):
    conn = sqlite3.connect(db_proc)
    cur = conn.cursor()
    cur.execute("DELETE FROM requirement_memory WHERE payload_json LIKE '%REQ-998811%' OR payload_json LIKE '%MSG-TEST-%'")
    print(f"Deleted KPMG test rows from requirement_memory: {cur.rowcount}")
    conn.commit()
    conn.close()

# 2. Search for 209160 in Outlook Graph API
try:
    from outlook_graph import acquire_token_from_env, iter_inbox_messages
    token = acquire_token_from_env()
    print(f"Graph token acquired. Scanning inbox for {mailbox}...")
    found_emails = []
    # Search top 200 messages for 209160
    for i, msg in enumerate(iter_inbox_messages(token, mailbox, limit=200)):
        subj = msg.get('subject', '')
        body_obj = msg.get('body', {}) or {}
        body = msg.get('bodyText', '') or msg.get('bodyHtml', '') or body_obj.get('content', '')
        sender = msg.get('from', {})
        if isinstance(sender, dict):
            sender_email = sender.get('emailAddress', {}).get('address', '')
        else:
            sender_email = str(sender)
        
        if '209160' in subj or '209160' in body:
            print(f"FOUND ACCENTURE EMAIL IN GRAPH! Subject: '{subj}' | From: '{sender_email}'")
            found_emails.append(msg)
            
    print(f"Total Graph emails matching 209160: {len(found_emails)}")
    if found_emails:
        with open('scratch/accenture_209160_msg.json', 'w', encoding='utf-8') as f:
            json.dump(found_emails[0], f, indent=2)
        print("Saved first matching email to scratch/accenture_209160_msg.json")
except Exception as e:
    import traceback
    traceback.print_exc()
