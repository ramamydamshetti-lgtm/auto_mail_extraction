import sqlite3
import json
import datetime

conn_pm = sqlite3.connect('data/processed_messages.db')
c_pm = conn_pm.cursor()

conn_mr = sqlite3.connect('data/metaforge_requirements.db')
c_mr = conn_mr.cursor()

print("=======================================================================")
print("STEP 1: TIMEZONE AND TIMESTAMP ANALYSIS")
print("=======================================================================")
local_now = datetime.datetime.now()
utc_now = datetime.datetime.now(datetime.timezone.utc)
print(f"System Local Time: {local_now.strftime('%Y-%m-%d %H:%M:%S')} (IST / UTC+05:30)")
print(f"System UTC Time  : {utc_now.strftime('%Y-%m-%d %H:%M:%S')} (UTC)")

# Sample timestamps from tables
print("\nTimestamp formats stored in DB:")
c_pm.execute("SELECT updated_at FROM pipeline_state ORDER BY updated_at DESC LIMIT 3")
print("pipeline_state.updated_at:", c_pm.fetchall())

c_pm.execute("SELECT created_at FROM filtered_log ORDER BY created_at DESC LIMIT 3")
print("filtered_log.created_at   :", c_pm.fetchall())

c_pm.execute("SELECT created_at FROM pending_reviews ORDER BY created_at DESC LIMIT 3")
print("pending_reviews.created_at:", c_pm.fetchall())

c_mr.execute("SELECT created_at FROM metaforge_requirements ORDER BY created_at DESC LIMIT 3")
print("metaforge_requirements.created_at:", c_mr.fetchall())

print("\n=======================================================================")
print("STEP 2: TODAY'S (2026-09-29) RAW SQL QUERIES AND COUNTS")
print("=======================================================================")

print("\n--- Query 2.1: Total Emails Ingested Today in pipeline_state ---")
sql_2_1 = "SELECT COUNT(*) FROM pipeline_state WHERE updated_at LIKE '2026-09-29%'"
c_pm.execute(sql_2_1)
res_2_1 = c_pm.fetchone()[0]
print(f"SQL: {sql_2_1}\nRESULT: {res_2_1}")

print("\n--- Query 2.2: Breakdown by pipeline_state for Today ---")
sql_2_2 = "SELECT state, COUNT(*) FROM pipeline_state WHERE updated_at LIKE '2026-09-29%' GROUP BY state"
c_pm.execute(sql_2_2)
res_2_2 = c_pm.fetchall()
print(f"SQL: {sql_2_2}\nRESULT: {res_2_2}")

print("\n--- Query 2.3: Breakdown of Rejections by Reason Today (filtered_log) ---")
sql_2_3 = "SELECT reason, stage, COUNT(*) FROM filtered_log WHERE created_at LIKE '2026-09-29%' GROUP BY reason, stage"
c_pm.execute(sql_2_3)
res_2_3 = c_pm.fetchall()
print(f"SQL: {sql_2_3}\nRESULT: {res_2_3}")

print("\n--- Query 2.4a: Total Active Requirements Created Today in metaforge_requirements ---")
sql_2_4a = "SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE created_at LIKE '2026-09-29%'"
c_mr.execute(sql_2_4a)
res_2_4a = c_mr.fetchall()
print(f"SQL: {sql_2_4a}\nRESULT COUNT: {len(res_2_4a)}")
for row in res_2_4a:
    p = json.loads(row[1])
    print(f"  Job ID: {row[0]} | Title: {p.get('job_title')} | Client: {p.get('requirement_from')} | Status: {p.get('job_status')} | Created: {row[2]}")

print("\n--- Query 2.4b: Total Requirements in Pending Reviews Created Today ---")
sql_2_4b = "SELECT id, graph_id, job_id, client_jd_id, payload_json, created_at FROM pending_reviews WHERE created_at LIKE '2026-09-29%'"
c_pm.execute(sql_2_4b)
res_2_4b = c_pm.fetchall()
print(f"SQL: {sql_2_4b}\nRESULT COUNT: {len(res_2_4b)}")
for row in res_2_4b:
    p = json.loads(row[4])
    print(f"  ID: {row[0]} | Job ID: {row[2]} | Title: {p.get('job_title')} | Client: {p.get('requirement_from')} | Status: {p.get('job_status')} | Created: {row[5]}")

print("\n--- Query 2.5: Total status_history entries written Today ---")
sql_2_5 = "SELECT * FROM status_history WHERE changed_at LIKE '2026-09-29%'"
c_pm.execute(sql_2_5)
res_2_5 = c_pm.fetchall()
print(f"SQL: {sql_2_5}\nRESULT COUNT: {len(res_2_5)}")
for r in res_2_5:
    print(" ", r)

print("\n--- Query 2.6: Pipeline state details indicating short-circuit / digest bypass ---")
sql_2_6 = "SELECT graph_id, state, detail, updated_at FROM pipeline_state WHERE updated_at LIKE '2026-09-29%' AND (detail LIKE '%status%' OR detail LIKE '%short%' OR detail LIKE '%digest%')"
c_pm.execute(sql_2_6)
res_2_6 = c_pm.fetchall()
print(f"SQL: {sql_2_6}\nRESULT COUNT: {len(res_2_6)}")
for r in res_2_6:
    print(" ", r)

conn_pm.close()
conn_mr.close()
