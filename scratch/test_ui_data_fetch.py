import sqlite3
import json

def fetch_all_requirements():
    results = []
    
    # Check metaforge_requirements.db
    try:
        conn = sqlite3.connect("file:data/metaforge_requirements.db?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements ORDER BY created_at DESC").fetchall()
        for r in rows:
            data = json.loads(r["payload_json"])
            req_id = data.get("client_jd_id") or data.get("job_id") or r["job_id"]
            results.append({
                "req_id": req_id,
                "source_db": "metaforge_requirements",
                "created_at": r["created_at"],
                "payload": data
            })
        conn.close()
    except Exception as e:
        print("metaforge_requirements.db read error:", e)

    # Check processed_messages.db (requirement_memory)
    try:
        conn = sqlite3.connect("file:data/processed_messages.db?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, requirement_from, job_title_norm, payload_json, created_at FROM requirement_memory ORDER BY created_at DESC").fetchall()
        for r in rows:
            data = json.loads(r["payload_json"])
            req_id = data.get("client_jd_id") or data.get("job_id") or f"MEM-{r['id']}"
            results.append({
                "req_id": req_id,
                "source_db": "requirement_memory",
                "created_at": r["created_at"],
                "payload": data
            })
        conn.close()
    except Exception as e:
        print("processed_messages.db read error:", e)

    print(f"Total requirements fetched across DBs: {len(results)}")
    if results:
        print("Sample req:", json.dumps(results[0], indent=2))

fetch_all_requirements()
