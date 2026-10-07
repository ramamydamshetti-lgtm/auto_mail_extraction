import sqlite3
import json

conn = sqlite3.connect("data/metaforge_requirements.db")
cur = conn.cursor()

rows = cur.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements WHERE lower(payload_json) LIKE '%accenture%' OR lower(payload_json) LIKE '%29th sep%'").fetchall()

print(f"Total matching Accenture records in metaforge_requirements.db: {len(rows)}")

acc_29_recs = []

for r in rows:
    try:
        p = json.loads(r[1])
        title = str(p.get("job_title") or "")
        req_from = str(p.get("requirement_from") or "")
        client_id = str(p.get("client_jd_id") or "")
        job_id = r[0]
        
        if "29th sep" in title.lower() or "accenture" in title.lower() or "accenture" in req_from.lower() or "29" in client_id:
            acc_29_recs.append((job_id, client_id, req_from, title, p.get("job_status"), p.get("mandatory_skills"), p.get("location")))
    except Exception:
        pass

print(f"\nFound {len(acc_29_recs)} Accenture 29th Sep demands:")
for idx, (jid, cid, rf, t, st, sk, loc) in enumerate(acc_29_recs):
    print(f"{idx+1}. ID: {jid} | ClientID: {cid} | Client: {rf} | Status: {st}")
    print(f"   Title: {t}")
    print(f"   Skills: {sk} | Location: {loc}")
