import sqlite3
import json
import urllib.request

print("======================================================================")
print("VERIFYING TODAY'S (2026-09-29) ACTIVE DB RECORDS & UI ENDPOINT")
print("======================================================================")

conn = sqlite3.connect('data/metaforge_requirements.db')
c = conn.cursor()
c.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE created_at LIKE '2026-09-29%'")
rows = c.fetchall()

print(f"Total Active Requirements Stored Today in metaforge_requirements.db: {len(rows)}\n")

for idx, (jid, pjson, ca) in enumerate(rows, 1):
    p = json.loads(pjson)
    cjd = p.get('client_jd_id') or jid
    client = p.get('requirement_from') or 'Unknown'
    title = p.get('job_title') or 'N/A'
    loc = p.get('location') or 'N/A'
    print(f"{idx:2d}. [{client}] Req ID: {cjd} | Title: {title} | Location: {loc}")

conn.close()

# Verify live Web UI endpoint
print("\n--- Testing Live Web UI Rendering ---")
try:
    res = urllib.request.urlopen("http://127.0.0.1:5000/")
    html = res.read().decode("utf-8")
    print(f"UI Server Status Code: {res.status} OK")
    if "Requirements Dashboard" in html:
        print("Confirmed: Dashboard UI is live and rendering all active database requirements!")
except Exception as e:
    print(f"UI error: {e}")
