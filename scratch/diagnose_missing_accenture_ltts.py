import sqlite3
import json
import csv
import os

print("======================================================================")
print("DIAGNOSING MISSING ACCENTURE (7) AND LTTS (9) REQUIREMENTS TODAY")
print("======================================================================")

# 1. Check Filtered Log for today's blocked messages
print("\n--- 1. FILTERED LOG (Blocked Messages Today) ---")
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT graph_id, subject, from_email, reason, stage, created_at FROM filtered_log").fetchall()
    print(f"Total entries in filtered_log: {len(rows)}")
    for r in rows:
        subj, fe, reason, stage, ca = r[1], r[2], r[3], r[4], r[5]
        if "accenture" in subj.lower() or "accenture" in fe.lower() or "iexcel" in fe.lower() or "ltts" in subj.lower() or "ltts" in fe.lower():
            print(f"  BLOCKED: [{stage}] {reason} | From: {fe} | Subj: {subj[:60]}")
    conn.close()

# 2. Check Pending Reviews for items needing review
print("\n--- 2. PENDING REVIEWS (Items needing review today) ---")
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT id, graph_id, job_id, client_jd_id, payload_json, review_fields, created_at FROM pending_reviews").fetchall()
    print(f"Total entries in pending_reviews: {len(rows)}")
    for r in rows:
        p = json.loads(r[4])
        rf = str(p.get("requirement_from") or "").lower()
        title = str(p.get("job_title") or "")
        rev = r[5]
        if "accenture" in rf or "ltts" in rf or "iexcel" in str(p).lower():
            print(f"  PENDING: [{rf.upper()}] Job ID: {r[2]} | Reason: {rev} | Title: {title[:60]}")
    conn.close()

# 3. Check Pipeline State (Skipped vs Processing vs Pending Sync)
print("\n--- 3. PIPELINE STATE BREAKDOWN ---")
if os.path.exists("data/processed_messages.db"):
    conn = sqlite3.connect("data/processed_messages.db")
    cur = conn.cursor()
    rows = cur.execute("SELECT state, count(*) FROM pipeline_state GROUP BY state").fetchall()
    for state, cnt in rows:
        print(f"  State '{state}': {cnt} messages")
    
    # Check details of skipped messages
    skipped_rows = cur.execute("SELECT graph_id, updated_at, detail FROM pipeline_state WHERE state='skipped' ORDER BY updated_at DESC LIMIT 15").fetchall()
    print("\n  Recent Skipped Details:")
    for gid, up, det in skipped_rows:
        print(f"    - {gid[:15]}... | Updated: {up} | Reason: {det}")
    conn.close()

# 4. Check Raw Inbox / Fetched Emails for Accenture & LTTS
print("\n--- 4. RAW FETCHED MESSAGES IN TODAY_FETCH.CSV / LATEST_200.JSON ---")
for fpath in ["today_fetch.csv", "latest_200.json", "latest_500_all.json"]:
    if os.path.exists(fpath):
        print(f"\nScanning {fpath}...")
        if fpath.endswith(".csv"):
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                acc_cnt = 0
                ltts_cnt = 0
                for row in reader:
                    subj = str(row.get("subject") or "").lower()
                    fe = str(row.get("from_email") or "").lower()
                    body = str(row.get("body_normalized") or "").lower()
                    if "accenture" in subj or "accenture" in body or "iexcel.co.in" in fe:
                        acc_cnt += 1
                        print(f"  ACCENTURE MSG #{acc_cnt}: Subj='{row.get('subject')}' | From='{row.get('from_email')}'")
                    if "ltts" in subj or "ltts" in body or "ltts.com" in fe or "l&t" in body:
                        ltts_cnt += 1
                        print(f"  LTTS MSG #{ltts_cnt}: Subj='{row.get('subject')}' | From='{row.get('from_email')}'")
        elif fpath.endswith(".json"):
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
                if isinstance(data, list):
                    acc_cnt = 0
                    ltts_cnt = 0
                    for row in data:
                        subj = str(row.get("subject") or "").lower()
                        fe = str(row.get("from_email") or "").lower()
                        body = str(row.get("body_normalized") or row.get("body_plain") or "").lower()
                        if "accenture" in subj or "accenture" in body or "iexcel.co.in" in fe:
                            acc_cnt += 1
                        if "ltts" in subj or "ltts" in body or "ltts.com" in fe:
                            ltts_cnt += 1
                    print(f"  Total Accenture matches in {fpath}: {acc_cnt}")
                    print(f"  Total LTTS matches in {fpath}: {ltts_cnt}")
