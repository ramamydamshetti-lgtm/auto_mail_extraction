import sqlite3
import json
import os
from pathlib import Path

db_path = Path("recruiter_app.db")
if not db_path.exists():
    print("DB file recruiter_app.db does not exist")
    exit(0)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables found in DB: {tables}")

target_date = "2026-09-30"

# Check client_requirements
if "client_requirements" in tables:
    rows = cursor.execute("SELECT client_jd_id, requirement_from, status, payload_json, created_at FROM client_requirements").fetchall()
    matched = []
    for r in rows:
        created = r["created_at"] or ""
        payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        demand_date = payload.get("demand_received_date") or payload.get("receivedDateTime") or ""
        if target_date in created or target_date in demand_date:
            matched.append((r["client_jd_id"], payload.get("job_title"), r["requirement_from"], demand_date or created))
    print(f"\n[client_requirements] Total matching 2026-09-30: {len(matched)}")
    for m in matched:
        print(f"  - {m[0]} | {m[1]} | {m[2]} | Date: {m[3]}")

# Check metaforge_requirements if present
if "metaforge_requirements" in tables:
    rows = cursor.execute("SELECT job_id, payload_json, created_at FROM metaforge_requirements").fetchall()
    matched = []
    for r in rows:
        created = r["created_at"] or ""
        payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        demand_date = payload.get("demand_received_date") or payload.get("receivedDateTime") or ""
        if target_date in created or target_date in demand_date:
            matched.append((r["job_id"], payload.get("job_title"), payload.get("requirement_from"), demand_date or created))
    print(f"\n[metaforge_requirements] Total matching 2026-09-30: {len(matched)}")
    for m in matched:
        print(f"  - {m[0]} | {m[1]} | {m[2]} | Date: {m[3]}")

# Check requirement_memory
if "requirement_memory" in tables:
    rows = cursor.execute("SELECT id, requirement_from, job_title_norm, payload_json, created_at FROM requirement_memory").fetchall()
    matched = []
    for r in rows:
        created = r["created_at"] or ""
        payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        demand_date = payload.get("demand_received_date") or payload.get("receivedDateTime") or ""
        if target_date in created or target_date in demand_date:
            matched.append((f"MEM-{r['id']}", payload.get("job_title"), r["requirement_from"], demand_date or created))
    print(f"\n[requirement_memory] Total matching 2026-09-30: {len(matched)}")
    for m in matched:
        print(f"  - {m[0]} | {m[1]} | {m[2]} | Date: {m[3]}")

# Check pending_reviews
if "pending_reviews" in tables:
    rows = cursor.execute("SELECT job_id, client_jd_id, payload_json, created_at FROM pending_reviews").fetchall()
    matched = []
    for r in rows:
        created = r["created_at"] or ""
        payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        demand_date = payload.get("demand_received_date") or payload.get("receivedDateTime") or ""
        if target_date in created or target_date in demand_date:
            matched.append((r["client_jd_id"] or r["job_id"], payload.get("job_title"), payload.get("requirement_from"), demand_date or created))
    print(f"\n[pending_reviews] Total matching 2026-09-30: {len(matched)}")
    for m in matched:
        print(f"  - {m[0]} | {m[1]} | {m[2]} | Date: {m[3]}")

conn.close()
