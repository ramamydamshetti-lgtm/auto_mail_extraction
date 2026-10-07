import sqlite3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

db_paths = ['data/metaforge_requirements.db', 'data/processed_messages.db']

# 1. Clean KPMG / test data from databases
for db_path in db_paths:
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"=== DB: {db_path} ===")
        for table in tables:
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            query_str = []
            if 'client_jd_id' in cols:
                query_str.append("client_jd_id LIKE '%REQ-998811%'")
                query_str.append("client_jd_id LIKE '%MSG-TEST-%'")
            if 'job_id' in cols:
                query_str.append("job_id LIKE '%REQ-998811%'")
                query_str.append("job_id LIKE '%MSG-TEST-%'")
            if 'message_id' in cols:
                query_str.append("message_id LIKE '%MSG-TEST-%'")
            if query_str:
                where_clause = ' OR '.join(query_str)
                count = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}").fetchone()[0]
                print(f"Found {count} synthetic test rows in {table}")
                if count > 0:
                    cur.execute(f"DELETE FROM {table} WHERE {where_clause}")
                    conn.commit()
                    print(f"Deleted {count} rows from {table}")
        conn.close()

# 2. Search for 209160 in requirements DB
if os.path.exists('data/metaforge_requirements.db'):
    conn = sqlite3.connect('data/metaforge_requirements.db')
    cur = conn.cursor()
    rows = cur.execute("SELECT job_id, client_jd_id, company, raw_email_body, subject FROM requirements WHERE client_jd_id LIKE '%209160%' OR raw_email_body LIKE '%209160%' OR subject LIKE '%209160%'").fetchall()
    print(f"\n=== DB Requirements matching 209160: {len(rows)} ===")
    for r in rows:
        print(f"job_id: {r[0]} | client_jd_id: {r[1]} | company: {r[2]} | subject: {r[4]}")
    conn.close()
