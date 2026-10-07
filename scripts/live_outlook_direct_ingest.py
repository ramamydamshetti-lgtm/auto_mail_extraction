import os
import sys
import sqlite3
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))

from config import Settings
from processed_store import ProcessedStore
from outlook_graph import acquire_token_from_env, iter_inbox_messages
from metaforge_api import IdAllocator
from main import process_single_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_ingest")

print("======================================================================")
print("LIVE OUTLOOK INBOX DIRECT INGESTION & UI DATABASE REFRESH")
print("======================================================================")

db_processed = "data/processed_messages.db"
db_metaforge = "data/metaforge_requirements.db"

# 1. Clear out stale/cached test data from SQLite databases
if os.path.exists(db_metaforge):
    conn = sqlite3.connect(db_metaforge)
    conn.execute("DELETE FROM metaforge_requirements")
    conn.execute("UPDATE mf_sequences SET value=0")
    conn.commit()
    conn.close()
    print("Cleared stale records from data/metaforge_requirements.db")

if os.path.exists(db_processed):
    conn = sqlite3.connect(db_processed)
    conn.execute("DELETE FROM pipeline_state")
    conn.execute("DELETE FROM pending_reviews")
    conn.execute("DELETE FROM requirement_memory")
    conn.execute("DELETE FROM filtered_log")
    conn.commit()
    conn.close()
    print("Cleared stale state/memory records from data/processed_messages.db")

# 2. Connect live to Microsoft Graph API and fetch Outlook emails
print("\nAcquiring live Microsoft Graph API token from Azure AD...")
try:
    token = acquire_token_from_env()
    print("Authentication SUCCESSful!\n")
except Exception as e:
    print(f"CRITICAL ERROR acquiring Outlook token: {e}")
    sys.exit(1)

mailbox = os.getenv("MAILBOX_UPN", "recruitment.application@metaforgeit.com").strip()
settings = Settings.from_env()
allocator = IdAllocator(db_metaforge)

print(f"Fetching live emails directly from Outlook Inbox ({mailbox})...\n")

total_fetched = 0
total_extracted_synced = 0

with ProcessedStore(db_processed) as store:
    for raw in iter_inbox_messages(token, mailbox, limit=50):
        total_fetched += 1
        gid = raw.get("id") or ""
        subj = str(raw.get("subject") or "")
        from_obj = raw.get("from") or {}
        ea = from_obj.get("emailAddress") or {}
        fe = str(ea.get("address") or "").strip()
        recv_dt = str(raw.get("receivedDateTime") or "")
        
        print(f"Processing Live Email #{total_fetched} [{fe}]: '{subj[:60]}'")
        
        try:
            synced_count = process_single_message(
                raw,
                token=token,
                mailbox=mailbox,
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=False,
            )
            total_extracted_synced += synced_count
            print(f"  -> Extracted & Synced Requirements: {synced_count}")
        except Exception as ex:
            print(f"  -> Processing Error on message {gid[:20]}: {ex}")

# 3. Check pending_reviews and sync any ready items to metaforge_requirements.db
if os.path.exists(db_processed):
    conn_pm = sqlite3.connect(db_processed)
    conn_mf = sqlite3.connect(db_metaforge)
    c_pm = conn_pm.cursor()
    c_mf = conn_mf.cursor()
    
    c_pm.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews")
    pr_rows = c_pm.fetchall()
    
    pr_synced = 0
    for pid, gid, jid, cjd, pjson, ca in pr_rows:
        p = json.loads(pjson)
        job_title = str(p.get("job_title") or "").strip()
        
        # Ensure non-empty valid job title
        if job_title and job_title.lower() != "untitled role":
            final_jid = jid if jid and jid != "STATUS-UNMATCHED" else f"REQ-LIVE-{pid:03d}"
            final_cjd = cjd if cjd and cjd != "STATUS-UNMATCHED" else (p.get("client_jd_id") or final_jid)
            p["job_id"] = final_jid
            p["client_jd_id"] = final_cjd
            
            c_mf.execute(
                "INSERT OR REPLACE INTO metaforge_requirements(job_id, payload_json, created_at) VALUES (?, ?, ?)",
                (final_jid, json.dumps(p, ensure_ascii=False), ca)
            )
            pr_synced += 1
            
    conn_mf.commit()
    conn_mf.close()
    conn_pm.close()
    print(f"\nSynced {pr_synced} valid extracted requirement(s) from pending queue to live DB.")

print("\n======================================================================")
print("LIVE INGESTION & UI SYNC COMPLETE:")
print(f"  - Total Live Outlook Emails Processed : {total_fetched}")
print(f"  - Total Requirements Synced to UI DB   : {total_extracted_synced + pr_synced}")
print("======================================================================")
