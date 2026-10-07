import sqlite3
import json

dbs = ['data/metaforge_requirements.db', 'data/processed_messages.db']

for db in dbs:
    print(f"=== Inspecting {db} ===")
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    
    for t in ['metaforge_requirements', 'requirement_memory', 'pending_reviews']:
        if t in tables:
            cur.execute(f"SELECT * FROM {t}")
            rows = cur.fetchall()
            cur.execute(f"PRAGMA table_info({t})")
            cols = [c[1] for c in cur.fetchall()]
            
            fixed_cnt = 0
            for r in rows:
                rdict = dict(zip(cols, r))
                pjson_str = rdict.get("payload_json")
                if not pjson_str:
                    continue
                try:
                    p = json.loads(pjson_str)
                except Exception:
                    continue
                
                req_from = str(p.get("requirement_from") or "").lower()
                client_lead = str(p.get("client_lead_poc") or "").lower()
                client_poc = str(p.get("client_poc") or "").lower()
                
                # Check if ITC Infotech has anusha or iexcel.co.in
                if "itc" in req_from and ("anusha" in client_lead or "anusha" in client_poc or "iexcel" in client_lead or "iexcel" in client_poc):
                    print(f"Found wrong POC for ITC record in {t}: {p.get('client_jd_id') or p.get('job_id')}")
                    print(f"  Old client_lead_poc: {p.get('client_lead_poc')}")
                    print(f"  Old client_poc     : {p.get('client_poc')}")
                    
                    # Fix payload
                    p["client_lead_poc"] = "Divya.Grover@itcinfotech.com"
                    p["client_poc"] = "Divya.Grover@itcinfotech.com"
                    new_pjson = json.dumps(p, ensure_ascii=False)
                    
                    if t == "metaforge_requirements":
                        cur.execute(f"UPDATE {t} SET payload_json = ? WHERE job_id = ?", (new_pjson, rdict["job_id"]))
                    elif t == "requirement_memory":
                        cur.execute(f"UPDATE {t} SET payload_json = ? WHERE id = ?", (new_pjson, rdict["id"]))
                    elif t == "pending_reviews":
                        cur.execute(f"UPDATE {t} SET payload_json = ? WHERE id = ?", (new_pjson, rdict["id"]))
                    fixed_cnt += 1
            
            if fixed_cnt > 0:
                conn.commit()
                print(f"  --> Fixed {fixed_cnt} records in table {t}")
    conn.close()
