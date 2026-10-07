import sqlite3
import json

print("=== FIXING ITC-2026-09-28-001 POC IN DATABASES ===")

dbs = ['data/metaforge_requirements.db', 'data/processed_messages.db']

for db_path in dbs:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    
    for t in ['metaforge_requirements', 'requirement_memory', 'pending_reviews']:
        if t in tables:
            cur.execute(f"SELECT * FROM {t}")
            rows = cur.fetchall()
            cur.execute(f"PRAGMA table_info({t})")
            cols = [c[1] for c in cur.fetchall()]
            
            fixed = 0
            for r in rows:
                rdict = dict(zip(cols, r))
                pjson = rdict.get("payload_json")
                if not pjson:
                    continue
                try:
                    p = json.loads(pjson)
                except Exception:
                    continue
                
                cjd = str(p.get("client_jd_id") or p.get("job_id") or "")
                req_from = str(p.get("requirement_from") or "").lower()
                
                if "itc" in req_from or "ITC-2026-09-28-001" in cjd:
                    old_lead = p.get("client_lead_poc")
                    old_poc = p.get("client_poc")
                    if old_lead != "Divya.Grover@itcinfotech.com" or old_poc != "Divya.Grover@itcinfotech.com":
                        print(f"Updating [{t}] {cjd}:")
                        print(f"  Old client_lead_poc : {old_lead}")
                        print(f"  Old client_poc      : {old_poc}")
                        p["client_lead_poc"] = "Divya.Grover@itcinfotech.com"
                        p["client_poc"] = "Divya.Grover@itcinfotech.com"
                        p["client_lead_poc_email"] = "Divya.Grover@itcinfotech.com"
                        new_json = json.dumps(p, ensure_ascii=False)
                        
                        if t == "metaforge_requirements":
                            cur.execute(f"UPDATE {t} SET payload_json = ? WHERE job_id = ?", (new_json, rdict["job_id"]))
                        elif t == "requirement_memory":
                            cur.execute(f"UPDATE {t} SET payload_json = ? WHERE id = ?", (new_json, rdict["id"]))
                        elif t == "pending_reviews":
                            cur.execute(f"UPDATE {t} SET payload_json = ? WHERE id = ?", (new_json, rdict["id"]))
                        fixed += 1
            if fixed > 0:
                conn.commit()
                print(f"  --> Updated {fixed} rows in {db_path} :: {t}")
    conn.close()

print("\nFix execution complete!")
