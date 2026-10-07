import json
import sys
import os
import sqlite3
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('.'))
load_dotenv()

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from processed_store import ProcessedStore
from outlook_graph import acquire_token_from_env, iter_inbox_messages

settings = Settings.from_env()
mailbox = settings.mailbox_upn

print(f"Acquiring Graph API token for mailbox: {mailbox}...")
token = acquire_token_from_env()
print("Graph token acquired successfully.")

allocator = IdAllocator(settings.metaforge_id_db)
store = ProcessedStore(settings.processed_db)

print(f"Reading entire Outlook Inbox for {mailbox} and processing requirements...")

total_messages = 0
total_synced_requirements = 0
skipped_messages = 0

for idx, msg in enumerate(iter_inbox_messages(token, mailbox, limit=500)):
    total_messages += 1
    gid = msg.get('id')
    subj = msg.get('subject', '')
    
    # Process message through pipeline
    count = process_single_message(
        raw=msg,
        token=token,
        mailbox=mailbox,
        settings=settings,
        allocator=allocator,
        store=store
    )
    
    if count > 0:
        total_synced_requirements += count
        print(f"  [{total_messages:3d}] Synced {count:2d} requirements | Subject: '{subj[:60]}'")
    else:
        skipped_messages += 1

print("\n=================================================================")
print(" OUTLOOK INBOX PROCESSING COMPLETE")
print("=================================================================")
print(f" Total emails examined           : {total_messages}")
print(f" Total new requirements synced   : {total_synced_requirements}")
print(f" Skipped / non-requirement emails : {skipped_messages}")

# Verify total stored requirements in metaforge_requirements.db
conn = sqlite3.connect(settings.metaforge_sqlite_path)
cur = conn.cursor()
total_db_rows = cur.execute("SELECT COUNT(*) FROM metaforge_requirements").fetchone()[0]
print(f" Total requirement rows in DB    : {total_db_rows}")
conn.close()
