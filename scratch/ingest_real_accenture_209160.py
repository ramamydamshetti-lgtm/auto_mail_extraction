import json
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('.'))
load_dotenv()

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from processed_store import ProcessedStore

settings = Settings.from_env()

with open('scratch/accenture_209160_msg.json', 'r', encoding='utf-8') as f:
    msg = json.load(f)

allocator = IdAllocator(settings.metaforge_sqlite_path)
store = ProcessedStore(settings.processed_db)

gid = msg.get('id')
if gid:
    import sqlite3
    conn = sqlite3.connect(settings.processed_db)
    cur = conn.cursor()
    cur.execute("DELETE FROM processed WHERE graph_id = ?", (gid,))
    cur.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (gid,))
    conn.commit()
    conn.close()

print(f"METAFORGE_MODE: {settings.metaforge_mode} | DB: {settings.metaforge_sqlite_path}")
print("Ingesting Accenture email into metaforge_requirements.db & processed_messages.db...")
count = process_single_message(
    raw=msg,
    token="",
    mailbox=settings.mailbox_upn,
    settings=settings,
    allocator=allocator,
    store=store
)

print(f"Ingestion result: synced count={count}")

# Verify 209160-1 in metaforge_requirements.db
import sqlite3
conn = sqlite3.connect('data/metaforge_requirements.db')
cur = conn.cursor()
rows = cur.execute("SELECT job_id, payload_json FROM metaforge_requirements WHERE payload_json LIKE '%209160-1%'").fetchall()
print(f"\nFound {len(rows)} matching rows in metaforge_requirements.db for 209160-1:")
for r in rows:
    p = json.loads(r[1])
    print(f"  job_id: {r[0]} | client_jd_id: {p.get('client_jd_id')} | title: {p.get('job_title')} | status: {p.get('job_status')} | company: {p.get('requirement_from')}")
conn.close()
