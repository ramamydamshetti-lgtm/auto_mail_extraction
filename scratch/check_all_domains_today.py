import sqlite3

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

c_pm.execute("SELECT from_email, subject, stage, reason FROM filtered_log WHERE created_at LIKE '2026-09-29%'")
fl_rows = c_pm.fetchall()

print("Filtered Log Senders Today:")
for r in fl_rows:
    print(f"  From: {r[0]:35s} | Stage: {r[2]:12s} | Reason: {r[3]:25s} | Subj: {r[1][:40]}")

conn_pm.close()
