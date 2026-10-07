import sqlite3
import json
import csv
import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath("."))

from config import Settings
from processed_store import ProcessedStore
from main import extract_and_map, process_single_message
from metaforge_api import IdAllocator

print("======================================================================")
print("RE-PROCESSING TODAY'S ACCENTURE (7) AND LTTS (9) OUTLOOK EMAILS")
print("======================================================================")

db_path = "data/processed_messages.db"
mf_db_path = "data/metaforge_requirements.db"

# Clear pipeline_state for skipped/pending_review today to allow fresh re-parsing
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM pipeline_state WHERE state IN ('skipped', 'pending_review')")
    cur.execute("DELETE FROM pending_reviews")
    conn.commit()
    print(f"Cleared stale pipeline_state and pending_reviews in {db_path}")
    conn.close()

# Inspect today_fetch.csv for Accenture and LTTS emails
if os.path.exists("today_fetch.csv"):
    with open("today_fetch.csv", "r", encoding="utf-8", errors="ignore") as f:
        reader = list(csv.DictReader(f))
        
    print(f"\nTotal fetched raw emails in today_fetch.csv: {len(reader)}")
    
    settings = Settings.from_env()
    allocator = IdAllocator(mf_db_path)
    
    acc_processed = 0
    ltts_processed = 0
    
    with ProcessedStore(db_path) as store:
        for idx, row in enumerate(reader):
            subj = str(row.get("subject") or "")
            fe = str(row.get("from_email") or "")
            body = str(row.get("body_normalized") or row.get("body_plain") or "")
            gid = str(row.get("graph_id") or f"MSG-RAW-{idx+1}")
            
            is_acc = "accenture" in subj.lower() or "accenture" in body.lower() or "iexcel" in fe.lower()
            is_ltts = "ltts" in subj.lower() or "ltts" in body.lower() or "ltts.com" in fe.lower() or "l&t" in subj.lower()
            
            if not (is_acc or is_ltts):
                continue
                
            raw_msg = {
                "id": gid,
                "subject": subj,
                "from": {"emailAddress": {"address": fe, "name": row.get("from_name") or ""}},
                "body": {"content": body, "contentType": "text"},
                "receivedDateTime": row.get("received_date_time") or "2026-09-29T10:00:00Z",
                "conversationId": row.get("internet_message_id") or gid,
                "hasAttachments": False,
            }
            
            res = process_single_message(
                raw_msg,
                token="",
                mailbox="recruitment.application@metaforgeit.com",
                settings=settings,
                allocator=allocator,
                store=store,
                skip_classifier=True,
            )
            
            if is_acc:
                acc_processed += res
            if is_ltts:
                ltts_processed += res
                
            print(f"Processed email #{idx+1} [{fe}]: '{subj[:50]}' -> Extracted rows: {res}")

    print("\n======================================================================")
    print(f"REPROCESSING COMPLETE:")
    print(f"  - Accenture Extracted Requirements: {acc_processed}")
    print(f"  - LTTS Extracted Requirements:      {ltts_processed}")
    print("======================================================================")
